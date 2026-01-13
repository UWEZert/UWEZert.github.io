from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Participant:
    uid: str
    token: str
    user_id: int
    chat_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    created_at: str
    status: str
    decided_at: Optional[str]
    decision: Optional[str]
    decision_by: Optional[int]
    decision_note: Optional[str]


class Storage:
    """Async SQLite storage.

    Concurrency strategy:
    - WAL mode allows readers while a writer is active
    - busy_timeout makes concurrent writers wait instead of failing fast
    - Every API call uses short transactions
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_lock = aiosqlite.Connection  # type: ignore
        self._initialized = False
        self._init_guard = None

    async def _ensure_init_guard(self):
        if self._init_guard is None:
            import asyncio

            self._init_guard = asyncio.Lock()

    async def init(self) -> None:
        await self._ensure_init_guard()
        async with self._init_guard:  # type: ignore
            if self._initialized:
                return
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("PRAGMA journal_mode=WAL;")
                await db.execute("PRAGMA synchronous=NORMAL;")
                await db.execute("PRAGMA busy_timeout=30000;")
                await db.execute("PRAGMA foreign_keys=ON;")

                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS participants (
                        uid TEXT PRIMARY KEY,
                        token TEXT NOT NULL UNIQUE,
                        user_id INTEGER NOT NULL,
                        chat_id INTEGER NOT NULL,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        created_at TEXT NOT NULL,
                        registered_ip TEXT,
                        status TEXT NOT NULL,
                        decided_at TEXT,
                        decision TEXT,
                        decision_by INTEGER,
                        decision_note TEXT
                    );
                    """
                )

                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS submissions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        uid TEXT NOT NULL,
                        received_at TEXT NOT NULL,
                        ip TEXT,
                        payload_json TEXT NOT NULL,
                        user_agent TEXT,
                        FOREIGN KEY(uid) REFERENCES participants(uid) ON DELETE CASCADE
                    );
                    """
                )

                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_submissions_uid ON submissions(uid);"
                )
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_participants_status ON participants(status);"
                )
                await db.commit()

            self._initialized = True

    async def register(
        self,
        *,
        uid: str,
        user_id: int,
        chat_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        ip: Optional[str],
    ) -> str:
        """Create/update participant and return confirmation token.

        Idempotent: if uid already exists, keeps existing token.
        """
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=30000;")
            await db.execute("PRAGMA foreign_keys=ON;")

            # If already registered, return token.
            cursor = await db.execute(
                "SELECT token FROM participants WHERE uid = ?;", (uid,)
            )
            row = await cursor.fetchone()
            if row and row[0]:
                return str(row[0])

            token = secrets.token_urlsafe(24)
            created_at = utc_now_iso()
            await db.execute(
                """
                INSERT INTO participants (
                    uid, token, user_id, chat_id, username, first_name, last_name,
                    created_at, registered_ip, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(uid) DO UPDATE SET
                    user_id=excluded.user_id,
                    chat_id=excluded.chat_id,
                    username=excluded.username,
                    first_name=excluded.first_name,
                    last_name=excluded.last_name;
                """,
                (
                    uid,
                    token,
                    int(user_id),
                    int(chat_id),
                    username,
                    first_name,
                    last_name,
                    created_at,
                    ip,
                    "registered",
                ),
            )
            await db.commit()
            return token

    async def confirm(
        self,
        *,
        uid: str,
        token: str,
        payload: dict[str, Any],
        ip: Optional[str],
        user_agent: Optional[str],
    ) -> None:
        """Store a submission and mark participant as submitted.

        Idempotent-ish: multiple submissions are stored, but status stays submitted.
        Token must match.
        """
        await self.init()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=30000;")
            await db.execute("PRAGMA foreign_keys=ON;")

            cursor = await db.execute(
                "SELECT token, status, decision FROM participants WHERE uid = ?;",
                (uid,),
            )
            row = await cursor.fetchone()
            if not row:
                raise ValueError("unknown_uid")
            expected_token, status, decision = row
            if str(expected_token) != str(token):
                raise ValueError("bad_token")
            if decision in ("approved", "rejected"):
                # Already decided: still accept storing submission, but do not change status.
                pass

            received_at = utc_now_iso()
            payload = dict(payload)
            payload.setdefault("uid", uid)
            payload.setdefault("received_at", received_at)

            await db.execute(
                """
                INSERT INTO submissions (uid, received_at, ip, payload_json, user_agent)
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    uid,
                    received_at,
                    ip,
                    json.dumps(payload, ensure_ascii=False),
                    user_agent,
                ),
            )

            # status progression: registered -> submitted (do not downgrade)
            await db.execute(
                """
                UPDATE participants
                SET status = CASE
                    WHEN status IN ('approved','rejected') THEN status
                    ELSE 'submitted'
                END
                WHERE uid = ?;
                """,
                (uid,),
            )
            await db.commit()

    async def pending(self, *, limit: int = 10) -> list[dict[str, Any]]:
        """Return latest pending submissions (submitted, not decided)."""
        await self.init()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=30000;")
            await db.execute("PRAGMA foreign_keys=ON;")

            cursor = await db.execute(
                """
                SELECT p.uid, p.user_id, p.chat_id, p.username, p.first_name, p.last_name,
                       p.created_at,
                       (SELECT s.received_at FROM submissions s WHERE s.uid = p.uid ORDER BY s.id DESC LIMIT 1) AS last_received_at
                FROM participants p
                WHERE p.status = 'submitted'
                  AND (p.decision IS NULL OR p.decision = '')
                ORDER BY last_received_at DESC
                LIMIT ?;
                """,
                (int(limit),),
            )
            rows = await cursor.fetchall()

            out: list[dict[str, Any]] = []
            for r in rows:
                out.append(
                    {
                        "uid": r[0],
                        "user_id": r[1],
                        "chat_id": r[2],
                        "username": r[3],
                        "first_name": r[4],
                        "last_name": r[5],
                        "created_at": r[6],
                        "last_received_at": r[7],
                    }
                )
            return out

    async def decide(
        self,
        *,
        uid: str,
        action: str,
        admin_id: int,
        note: Optional[str] = None,
    ) -> Participant:
        """Approve/reject a participant (idempotent)."""
        await self.init()
        action_norm = "approved" if action == "approve" else "rejected"

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=30000;")
            await db.execute("PRAGMA foreign_keys=ON;")

            cursor = await db.execute(
                "SELECT uid, token, user_id, chat_id, username, first_name, last_name, created_at, status, decided_at, decision, decision_by, decision_note FROM participants WHERE uid = ?;",
                (uid,),
            )
            row = await cursor.fetchone()
            if not row:
                raise ValueError("unknown_uid")

            decided_at = utc_now_iso()

            # Do not overwrite an existing decision with a different one.
            current_decision = row[10]
            if current_decision in ("approved", "rejected"):
                action_norm = str(current_decision)

            await db.execute(
                """
                UPDATE participants
                SET status = ?,
                    decision = ?,
                    decided_at = COALESCE(decided_at, ?),
                    decision_by = COALESCE(decision_by, ?),
                    decision_note = COALESCE(decision_note, ?)
                WHERE uid = ?;
                """,
                (
                    action_norm,
                    action_norm,
                    decided_at,
                    int(admin_id),
                    note,
                    uid,
                ),
            )
            await db.commit()

            cursor2 = await db.execute(
                "SELECT uid, token, user_id, chat_id, username, first_name, last_name, created_at, status, decided_at, decision, decision_by, decision_note FROM participants WHERE uid = ?;",
                (uid,),
            )
            row2 = await cursor2.fetchone()
            assert row2 is not None
            return Participant(
                uid=row2[0],
                token=row2[1],
                user_id=int(row2[2]),
                chat_id=int(row2[3]),
                username=row2[4],
                first_name=row2[5],
                last_name=row2[6],
                created_at=row2[7],
                status=row2[8],
                decided_at=row2[9],
                decision=row2[10],
                decision_by=row2[11],
                decision_note=row2[12],
            )

    async def reset(self) -> None:
        """Wipe all data."""
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=30000;")
            await db.execute("PRAGMA foreign_keys=ON;")
            await db.execute("DELETE FROM submissions;")
            await db.execute("DELETE FROM participants;")
            await db.commit()

    async def get_participant(self, uid: str) -> Optional[Participant]:
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=30000;")
            await db.execute("PRAGMA foreign_keys=ON;")
            cursor = await db.execute(
                "SELECT uid, token, user_id, chat_id, username, first_name, last_name, created_at, status, decided_at, decision, decision_by, decision_note FROM participants WHERE uid = ?;",
                (uid,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return Participant(
                uid=row[0],
                token=row[1],
                user_id=int(row[2]),
                chat_id=int(row[3]),
                username=row[4],
                first_name=row[5],
                last_name=row[6],
                created_at=row[7],
                status=row[8],
                decided_at=row[9],
                decision=row[10],
                decision_by=row[11],
                decision_note=row[12],
            )
