# db.py
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
    contest_id: int


class Storage:
    """Async SQLite storage."""

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

                # --- Таблица конкурсов ---
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS contests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        created_at TEXT NOT NULL DEFAULT (datetime('now')),
                        is_active BOOLEAN NOT NULL DEFAULT 0
                    );
                    """
                )

                # --- Таблица участников ---
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
                        status TEXT NOT NULL DEFAULT 'registered', -- 'registered', 'submitted_for_current_contest', 'awaiting_approval', 'approved', 'rejected'
                        decided_at TEXT,
                        decision TEXT,
                        decision_by INTEGER,
                        decision_note TEXT,
                        contest_id INTEGER NOT NULL DEFAULT 1 REFERENCES contests(id) -- Ссылка на конкурс
                    );
                    """
                )

                # --- Таблица сабмитов ---
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

                # --- Индексы ---
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_submissions_uid ON submissions(uid);"
                )
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_participants_status ON participants(status);"
                )
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_participants_contest_id ON participants(contest_id);" # Добавлен индекс
                )
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_participants_status_contest ON participants(status, contest_id);" # Добавлен составной индекс
                )

                await db.commit()

            self._initialized = True

    async def create_default_contest_if_not_exists(self):
        """Создает дефолтный конкурс, если он не существует."""
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT OR IGNORE INTO contests (name, is_active) VALUES (?, 1)", ("Default Contest",))
            await db.commit()

    async def create_contest(self, name: str) -> int:
        """Создает новый конкурс и делает его активным."""
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            # Деактивировать текущий активный конкурс
            await db.execute("UPDATE contests SET is_active = 0 WHERE is_active = 1")
            # Создать новый активный конкурс
            await db.execute("INSERT INTO contests (name, is_active) VALUES (?, 1)", (name,))
            cursor = await db.execute("SELECT last_insert_rowid()")
            new_contest_id = (await cursor.fetchone())[0]
            await db.commit()
            print(f"INFO: New contest '{name}' (ID: {new_contest_id}) created and activated.")
            return new_contest_id

    async def get_active_contest_id(self) -> Optional[int]:
        """Возвращает ID активного конкурса."""
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT id FROM contests WHERE is_active = 1 LIMIT 1")
            row = await cursor.fetchone()
            return row[0] if row else None

    async def get_all_contests(self) -> list[dict[str, Any]]:
        """Возвращает список всех конкурсов."""
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT id, name, created_at, is_active FROM contests ORDER BY created_at DESC")
            rows = await cursor.fetchall()
            return [{"id": r[0], "name": r[1], "created_at": r[2], "is_active": bool(r[3])} for r in rows]

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
        """Create/update participant and return confirmation token. Idempotent."""
        await self.init()
        active_contest_id = await self.get_active_contest_id()
        if not active_contest_id:
             print("WARNING: No active contest found, using default ID 1 for registration.")
             active_contest_id = 1 # Дефолтный ID

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=30000;")
            await db.execute("PRAGMA foreign_keys=ON;")

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
                    created_at, registered_ip, status, contest_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    "registered", # Начальный статус
                    active_contest_id, # Привязка к активному конкурсу
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
        """Store a submission and mark participant as submitted. Token must match."""
        await self.init()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=30000;")
            await db.execute("PRAGMA foreign_keys=ON;")

            cursor = await db.execute(
                "SELECT token, status, decision, contest_id FROM participants WHERE uid = ?;",
                (uid,),
            )
            row = await cursor.fetchone()
            if not row:
                raise ValueError("unknown_uid")
            expected_token, status, decision, contest_id = row
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

            # status progression: registered -> submitted_for_current_contest -> awaiting_approval -> approved/rejected
            await db.execute(
                """
                UPDATE participants
                SET status = CASE
                    WHEN status IN ('approved','rejected') THEN status
                    ELSE 'submitted_for_current_contest'
                END
                WHERE uid = ?;
                """,
                (uid,),
            )
            await db.commit()

    async def pending(self, *, limit: int = 10) -> list[dict[str, Any]]:
        """Return latest pending submissions (awaiting approval for current contest)."""
        # await self.init() # Вызов init() не должен быть здесь, если он уже вызывается в других местах при старте
        active_contest_id = await self.get_active_contest_id()
        if not active_contest_id:
             print("WARNING: No active contest found for pending list.")
             return []

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=30000;")
            await db.execute("PRAGMA foreign_keys=ON;")

            cursor = await db.execute(
                """
                SELECT p.uid, p.user_id, p.chat_id, p.username, p.first_name, p.last_name,
                       p.created_at,
                       (SELECT s.received_at FROM submissions s WHERE s.uid = p.uid ORDER BY s.id DESC LIMIT 1) AS last_received_at
                FROM participants p
                WHERE p.contest_id = ? AND p.status = 'awaiting_approval'
                  AND (p.decision IS NULL OR p.decision = '')
                ORDER BY last_received_at DESC
                LIMIT ?;
                """,
                (active_contest_id, int(limit)),
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

    # --- НОВЫЙ МЕТОД ДЛЯ POLLING ---
    async def get_uids_by_status_for_current_contest(self, status: str) -> list[str]:
        """Возвращает список UID участников с определенным статусом в активном конкурсе."""
        await self.init()
        active_contest_id = await self.get_active_contest_id()
        if not active_contest_id:
             print(f"WARNING: No active contest found for polling status '{status}'.")
             return []

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=30000;")
            await db.execute("PRAGMA foreign_keys=ON;")

            cursor = await db.execute(
                "SELECT uid FROM participants WHERE contest_id = ? AND status = ?;",
                (active_contest_id, status),
            )
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def set_status_to_awaiting_approval(self, uid: str) -> Optional[Participant]:
        """Updates participant status to awaiting_approval if possible."""
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=30000;")
            await db.execute("PRAGMA foreign_keys=ON;")

            # Проверяем текущий статус перед обновлением (атомарная операция)
            cursor = await db.execute("SELECT status FROM participants WHERE uid = ? AND status = 'submitted_for_current_contest';", (uid,))
            row = await cursor.fetchone()
            if not row:
                # Статус не 'submitted_for_current_contest', нельзя обновить или уже обновлен
                return None

            # Обновляем статус на 'awaiting_approval'
            await db.execute("UPDATE participants SET status = 'awaiting_approval' WHERE uid = ? AND status = 'submitted_for_current_contest';", (uid,))
            rows_affected = db.rowcount
            await db.commit()

            if rows_affected > 0:
                 # Успешно обновлено, возвращаем обновленные данные
                 return await self.get_participant(uid)
            else:
                 # Не обновлено (гонка), возвращаем None
                 return None

    async def get_last_submission_info(self, uid: str) -> Optional[dict[str, Any]]:
        """Returns the most recent submission details for a participant."""
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT received_at, ip, user_agent, payload_json FROM submissions WHERE uid = ? ORDER BY id DESC LIMIT 1",
                (uid,)
            )
            row = await cursor.fetchone()
            if row:
                 payload_dict = {}
                 try:
                     payload_dict = json.loads(row[3]) # payload_json
                 except json.JSONDecodeError:
                     print(f"WARNING: Could not decode payload JSON for UID {uid}")
                 return {"received_at": row[0], "ip": row[1], "ua": row[2], "payload_json": payload_dict}
            return None

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
                "SELECT uid, token, user_id, chat_id, username, first_name, last_name, created_at, status, decided_at, decision, decision_by, decision_note, contest_id FROM participants WHERE uid = ?;",
                (uid,),
            )
            row = await cursor.fetchone()
            if not row:
                raise ValueError("unknown_uid")

            decided_at = utc_now_iso()

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
                "SELECT uid, token, user_id, chat_id, username, first_name, last_name, created_at, status, decided_at, decision, decision_by, decision_note, contest_id FROM participants WHERE uid = ?;",
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
                contest_id=row2[13],
            )

    async def reset(self) -> None: """Wipe all data.""" # Используйте с осторожностью
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=30000;")
            await db.execute("PRAGMA foreign_keys=ON;")
            await db.execute("DELETE FROM submissions;")
            await db.execute("DELETE FROM participants;")
            await db.execute("DELETE FROM contests;") # Удаляет и конкурсы!
            await db.commit()

    async def get_participant(self, uid: str) -> Optional[Participant]:
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=30000;")
            await db.execute("PRAGMA foreign_keys=ON;")
            cursor = await db.execute(
                "SELECT uid, token, user_id, chat_id, username, first_name, last_name, created_at, status, decided_at, decision, decision_by, decision_note, contest_id FROM participants WHERE uid = ?;",
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
                contest_id=row[13],
            )
