# db.py
from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite
import logging # Добавляем импорт logging

# Настройка логирования (лучше поместить это в начало файла или в ваш server.py)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__) # Создаем логгер для этого файла


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
        logger.info(f"Storage initialized with DB path: {self.db_path}") # Логируем путь
        db_dir = os.path.dirname(self.db_path) or "."
        logger.info(f"DB directory: {db_dir}") # Логируем директорию
        os.makedirs(db_dir, exist_ok=True) # Создаем директорию, если её нет
        logger.info(f"DB directory exists: {os.path.exists(db_dir)}") # Проверяем существование
        logger.info(f"DB directory is writable: {os.access(db_dir, os.W_OK)}") # Проверяем права на запись
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
                logger.debug("Storage already initialized, skipping init.") # Отладочный лог
                return

            logger.info(f"Initializing database at: {self.db_path}") # Информационный лог
            try:
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
                    logger.info("Database tables initialized successfully.") # Информационный лог

                self._initialized = True
                logger.info("Storage initialization completed successfully.") # Информационный лог
            except Exception as e:
                logger.error(f"Failed to initialize database at {self.db_path}: {e}", exc_info=True) # Логируем ошибку с traceback
                raise # Перебрасываем исключение, чтобы сервер знал, что инициализация провалилась

    # ... (остальные методы остаются без изменений, но можно добавить логирование и туда для отладки)
    # ... (скопируйте остальную часть кода из предыдущей версии db.py, которую я дал, включая методы reset и get_participant)

    # --- Все остальные методы остаются без изменений, за исключением возможного добавления логирования ---
    # (Пример добавления логирования в register)
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
        logger.debug(f"Register called for UID: {uid}") # Добавляем отладочный лог
        await self.init()
        active_contest_id = await self.get_active_contest_id()
        if not active_contest_id:
             logger.warning("No active contest found, using default ID 1 for registration.")
             active_contest_id = 1 # Дефолтный ID

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=30000;")
            await db.execute("PRAGMA foreign_keys=ON;")

            cursor = await db.execute(
                "SELECT token FROM participants WHERE uid = ?;", (uid,)
            )
            row = await cursor.fetchone()
            if row and row[0]:
                logger.debug(f"UID {uid} already registered, returning existing token.")
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
            logger.info(f"New participant registered: UID={uid}, User_ID={user_id}, Chat_ID={chat_id}")
            return token

    # ... (повторите аналогичное добавление логирования в другие методы, если потребуется)

    # ... (остальная часть методов, включая decide, reset, get_participant и т.д., без изменений, кроме логирования)
    # В методе decide, добавьте обработку случая, если row2 None:
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
            # Проверка на случай гонки условий между UPDATE и SELECT
            if not row2:
                 # Участник был удален или что-то пошло не так между UPDATE и SELECT
                 logger.error(f"Participant {uid} disappeared after update in decide method.")
                 raise ValueError("Participant disappeared after update")
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

    # ... (остальные методы, включая reset и get_participant) ...
    async def reset(self) -> None:
        """Wipe all data.""" # Используйте с осторожностью
        await self.init() # Убедитесь, что БД инициализирована перед очисткой
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA busy_timeout=30000;")
            await db.execute("PRAGMA foreign_keys=ON;")
            await db.execute("DELETE FROM submissions;")
            await db.execute("DELETE FROM participants;")
            await db.execute("DELETE FROM contests;") # Удаляет и конкурсы!
            await db.commit()
        # После очистки и коммита, возможно, стоит повторно создать дефолтные таблицы/конкурсы
        # await self.init() # Это может быть избыточно, так как init уже вызван выше, но если таблицы удаляются полностью, то может понадобиться.
        # Лучше вызвать отдельную функцию инициализации или создать дефолтный конкурс снова:
        await self.create_default_contest_if_not_exists()
        logger.info("Database reset completed.")

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
