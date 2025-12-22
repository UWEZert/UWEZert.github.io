import os
import json
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


# -------------------- ENV --------------------
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
ADMIN_ID = int((os.getenv("ADMIN_ID") or "0").strip() or "0")

DB_PATH = os.getenv("DB_PATH", "participants.db").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in Railway env vars")
if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID is missing/invalid in Railway env vars")


# -------------------- Helpers --------------------
def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def safe_json(obj) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)

def country_flag_emoji(country_code: str) -> str:
    """
    'RU' -> 🇷🇺
    """
    cc = (country_code or "").strip().upper()
    if len(cc) != 2 or not cc.isalpha():
        return ""
    return chr(ord(cc[0]) + 127397) + chr(ord(cc[1]) + 127397)


# -------------------- DB --------------------
def db_connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def db_init():
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS participants (
        uid TEXT PRIMARY KEY,
        num INTEGER,
        status TEXT DEFAULT 'pending',

        user_id INTEGER,
        username TEXT,
        first_name TEXT,

        reg_ts TEXT,
        confirm_ts TEXT,

        ip TEXT,
        country TEXT,
        country_code TEXT,
        city TEXT,

        time_local TEXT,
        time_utc TEXT,
        user_agent TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS meta (
        k TEXT PRIMARY KEY,
        v TEXT
    );
    """)

    cur.execute("INSERT OR IGNORE INTO meta (k, v) VALUES ('counter', '0');")
    conn.commit()
    conn.close()

def db_next_number() -> int:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT v FROM meta WHERE k='counter'")
    row = cur.fetchone()
    cur_val = int(row["v"]) if row else 0
    new_val = cur_val + 1
    cur.execute("UPDATE meta SET v=? WHERE k='counter'", (str(new_val),))
    conn.commit()
    conn.close()
    return new_val

def db_reset_all():
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM participants;")
    cur.execute("UPDATE meta SET v='0' WHERE k='counter';")
    conn.commit()
    conn.close()

def db_get(uid: str):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM participants WHERE uid=?", (uid,))
    row = cur.fetchone()
    conn.close()
    return row

def db_insert_register(uid: str, user_id: int, username: Optional[str], first_name: Optional[str]):
    num = db_next_number()
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO participants (uid, num, status, user_id, username, first_name, reg_ts)
        VALUES (?, ?, 'pending', ?, ?, ?, ?)
        ON CONFLICT(uid) DO UPDATE SET
            user_id=excluded.user_id,
            username=excluded.username,
            first_name=excluded.first_name
    """, (uid, num, user_id, username, first_name, now_utc_iso()))
    conn.commit()
    conn.close()
    return num

def db_update_confirm(uid: str, payload: dict):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("""
        UPDATE participants SET
            confirm_ts=?,
            ip=?,
            country=?,
            country_code=?,
            city=?,
            time_local=?,
            time_utc=?,
            user_agent=?
        WHERE uid=?
    """, (
        now_utc_iso(),
        payload.get("ip"),
        payload.get("country"),
        payload.get("country_code"),
        payload.get("city"),
        payload.get("time_local"),
        payload.get("time_utc"),
        payload.get("user_agent"),
        uid
    ))
    conn.commit()
    conn.close()

def db_set_status(uid: str, status: str):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("UPDATE participants SET status=? WHERE uid=?", (status, uid))
    conn.commit()
    conn.close()


# -------------------- Telegram API --------------------
TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

async def tg_send_message(chat_id: int, text: str, reply_markup: Optional[dict] = None, disable_preview: bool = True):
    url = TELEGRAM_API.format(token=BOT_TOKEN, method="sendMessage")
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_preview,
    }
    if reply_markup:
        data["reply_markup"] = reply_markup

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json=data)
        if r.status_code != 200:
            logging.error("Telegram sendMessage failed: %s %s", r.status_code, r.text)
            raise HTTPException(status_code=500, detail="Telegram sendMessage failed")
        return r.json()

def admin_decision_keyboard(uid: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Одобрить", "callback_data": f"approve:{uid}"},
                {"text": "❌ Отклонить", "callback_data": f"reject:{uid}"},
            ]
        ]
    }


# -------------------- FastAPI --------------------
app = FastAPI(title="Perplexity Contest Server", version="1.0.0")

# CORS: чтобы GitHub Pages мог POST на Railway
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://uwezert.github.io",
        "http://localhost",
        "http://127.0.0.1",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

db_init()


# -------------------- Models --------------------
class RegisterIn(BaseModel):
    uid: str
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None

class ConfirmIn(BaseModel):
    uid: str

    time_local: Optional[str] = None
    time_utc: Optional[str] = None
    user_agent: Optional[str] = None

    ip: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    city: Optional[str] = None

class DecisionIn(BaseModel):
    uid: str
    action: str = Field(..., pattern="^(approve|reject)$")


# -------------------- Routes --------------------
@app.get("/")
async def root():
    return {"ok": True, "service": "perplexity-contest-server"}

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/register")
async def register(data: RegisterIn):
    # создаём/обновляем участника + номер
    num = db_insert_register(
        uid=data.uid,
        user_id=data.user_id,
        username=data.username,
        first_name=data.first_name
    )
    return {"ok": True, "uid": data.uid, "num": num}

@app.post("/confirm")
async def confirm(data: ConfirmIn):
    row = db_get(data.uid)
    if not row:
        raise HTTPException(status_code=404, detail="Unknown uid. User must /start first.")

    # сохраняем подтверждение
    db_update_confirm(data.uid, data.model_dump())

    # собираем сообщение админу
    username = row["username"] or ""
    uname = f"@{username}" if username else "(no username)"
    first_name = row["first_name"] or ""
    num = row["num"] or "?"
    flag = country_flag_emoji(data.country_code or "")
    country = data.country or "unknown"
    city = data.city or "unknown"
    ip = data.ip or "unknown"
    tloc = data.time_local or "unknown"
    tutc = data.time_utc or "unknown"

    admin_text = (
        f"🆕 <b>Новый участник #{num}</b>\n"
        f"UID: <code>{data.uid}</code>\n"
        f"Пользователь: {uname} ({first_name})\n\n"
        f"🌍 Локация: {flag} <b>{country}</b>, {city}\n"
        f"📡 IP: <code>{ip}</code>\n"
        f"🕒 Время (local): <code>{tloc}</code>\n"
        f"🕒 Время (UTC): <code>{tutc}</code>\n\n"
        f"Статус: <b>{row['status']}</b>"
    )

    # отправляем админу карточку + кнопки
    await tg_send_message(ADMIN_ID, admin_text, reply_markup=admin_decision_keyboard(data.uid))

    # пользователю — “мы получили ваши данные…”
    user_id = int(row["user_id"] or 0)
    if user_id:
        await tg_send_message(
            user_id,
            "✅ Мы получили ваши данные.\n"
            "После сверивания вам придёт подтверждение участия, ожидайте!"
        )

    return {"ok": True}

@app.post("/decision")
async def decision(data: DecisionIn):
    row = db_get(data.uid)
    if not row:
        raise HTTPException(status_code=404, detail="Unknown uid")

    status = "approved" if data.action == "approve" else "rejected"
    db_set_status(data.uid, status)

    # уведомляем участника
    user_id = int(row["user_id"] or 0)
    if user_id:
        if status == "approved":
            txt = "✅ Всё хорошо, вы участвуете в конкурсе, ожидайте результатов!"
        else:
            txt = "❌ К сожалению, участие не подтверждено."
        await tg_send_message(user_id, txt)

    return {"ok": True, "uid": data.uid, "status": status}

@app.post("/reset")
async def reset():
    db_reset_all()
    return {"ok": True, "reset": True}
