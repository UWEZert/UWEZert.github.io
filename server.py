import os
import json
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(Path(__file__).with_name(".env"))

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0").strip() or "0")

DATA_DIR = Path(os.getenv("DATA_DIR", ".")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_FILE = DATA_DIR / "db.json"  # хранит всё: users, confirms, decisions, counter

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in .env (server)")
if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID is missing/invalid in .env (server)")

app = FastAPI()

# CORS для GitHub Pages
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://uwezert.github.io",
        "http://localhost",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)


def load_db() -> Dict[str, Any]:
    if not DB_FILE.exists():
        return {"counter": 0, "users": {}, "confirms": {}, "decisions": {}}
    try:
        return json.loads(DB_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"counter": 0, "users": {}, "confirms": {}, "decisions": {}}


def save_db(db: Dict[str, Any]) -> None:
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


def country_flag_emoji(country_code: str) -> str:
    """
    country_code: 'RU', 'US', ...
    """
    if not country_code or len(country_code) != 2:
        return ""
    cc = country_code.upper()
    return chr(0x1F1E6 + (ord(cc[0]) - ord("A"))) + chr(0x1F1E6 + (ord(cc[1]) - ord("A")))


async def tg_send_message(chat_id: int, text: str, reply_markup: Optional[dict] = None) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()


@app.get("/")
async def root():
    return {"ok": True}


@app.get("/health")
async def health():
    return {"ok": True, "db_file": str(DB_FILE)}


@app.post("/reset")
async def reset():
    db = {"counter": 0, "users": {}, "confirms": {}, "decisions": {}}
    save_db(db)
    return {"ok": True}


@app.post("/register")
async def register(payload: dict):
    """
    payload:
      uid, user_id, chat_id, username, first_name
    """
    uid = str(payload.get("uid", "")).strip()
    user_id = payload.get("user_id")
    chat_id = payload.get("chat_id")

    if not uid or not user_id or not chat_id:
        return {"status": "error", "message": "uid/user_id/chat_id required"}

    db = load_db()
    db["users"][uid] = {
        "uid": uid,
        "user_id": int(user_id),
        "chat_id": int(chat_id),
        "username": payload.get("username"),
        "first_name": payload.get("first_name"),
        "registered_at": time.time(),
    }
    save_db(db)
    return {"ok": True}


@app.post("/confirm")
async def confirm(payload: dict):
    """
    payload приходит с сайта (confirm.js)
    должен содержать uid + данные ip/страны/города/время
    """
    uid = str(payload.get("uid", "")).strip()
    if not uid:
        return {"status": "error", "message": "uid required"}

    db = load_db()
    user = db["users"].get(uid)

    # если uid не найден — всё равно сохраним confirm, но админу покажем "не зарегистрирован"
    db["counter"] = int(db.get("counter", 0)) + 1
    number = db["counter"]

    confirm_data = {
        "number": number,
        "uid": uid,
        "received_at": time.time(),
        "time_utc": payload.get("time_utc"),
        "time_local": payload.get("time_local"),
        "tz": payload.get("tz"),
        "ip": payload.get("ip"),
        "country": payload.get("country"),
        "country_code": payload.get("country_code"),
        "city": payload.get("city"),
        "device": payload.get("device"),
        "user_agent": payload.get("userAgent") or payload.get("user_agent"),
    }
    db["confirms"][uid] = confirm_data
    save_db(db)

    # 3-е сообщение пользователю (после подтверждения на сайте)
    if user:
        try:
            await tg_send_message(
                user["chat_id"],
                "✅ Мы получили ваши данные, после сверивания вам придёт подтверждение в участии, ожидайте!"
            )
        except Exception as e:
            logging.error("Failed to message user: %s", e)

    # сообщение админу с кнопками
    uname = (user.get("username") if user else None) or "—"
    fname = (user.get("first_name") if user else None) or "—"
    cc = (confirm_data.get("country_code") or "").strip()
    flag = country_flag_emoji(cc)

    admin_text = (
        f"👤 <b>Новый участник</b> №{number}\n"
        f"UID: <code>{uid}</code>\n"
        f"Telegram: @{uname} ({fname})\n\n"
        f"📍 Локация: {flag} {confirm_data.get('country') or 'unknown'} / {confirm_data.get('city') or 'unknown'}\n"
        f"🌐 IP: {confirm_data.get('ip') or 'unknown'}\n"
        f"🕒 Time UTC: {confirm_data.get('time_utc') or 'unknown'}\n"
        f"🕒 Time local: {confirm_data.get('time_local') or 'unknown'}\n"
        f"🗺 TZ: {confirm_data.get('tz') or 'unknown'}\n"
    )

    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "✅ Одобрить", "callback_data": f"approve:{uid}"},
                {"text": "❌ Отклонить", "callback_data": f"reject:{uid}"},
            ]
        ]
    }

    try:
        await tg_send_message(ADMIN_ID, admin_text, reply_markup=reply_markup)
    except Exception as e:
        logging.error("Failed to message admin: %s", e)

    return {"ok": True, "number": number}


@app.post("/decision")
async def decision(payload: dict):
    uid = str(payload.get("uid", "")).strip()
    action = str(payload.get("action", "")).strip()  # approve / reject

    if action not in ("approve", "reject") or not uid:
        return {"status": "error", "message": "uid + action(approve|reject) required"}

    db = load_db()
    user = db["users"].get(uid)

    db["decisions"][uid] = {"uid": uid, "action": action, "at": time.time()}
    save_db(db)

    # уведомляем пользователя о решении
    if user:
        try:
            if action == "approve":
                await tg_send_message(user["chat_id"], "✅ Всё хорошо, вы участвуете в конкурсе, ожидайте результатов!")
            else:
                await tg_send_message(user["chat_id"], "❌ К сожалению, вы не прошли проверку условий.")
        except Exception as e:
            logging.error("Failed to message user about decision: %s", e)

    return {"ok": True}
