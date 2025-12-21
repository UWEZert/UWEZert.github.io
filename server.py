import os
import json
from pathlib import Path
from typing import Optional, Literal
from threading import Lock

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


# ================== ENV (Railway Variables) ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")  # обязателен
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # обязателен (твой TG id)
# ============================================================

if not BOT_TOKEN:
    # Сервер может стартовать, но любые попытки отправить сообщения упадут
    # Лучше упасть сразу, чтобы ты увидел причину в логах
    raise RuntimeError("BOT_TOKEN is not set in environment variables")

TG_SEND_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

DB_PATH = Path("participants.json")
DB_LOCK = Lock()


app = FastAPI()

# CORS: GitHub Pages -> Railway
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://uwezert.github.io", "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _init_db_if_needed() -> None:
    if not DB_PATH.exists():
        DB_PATH.write_text(json.dumps({"counter": 0, "participants": {}}, ensure_ascii=False, indent=2),
                           encoding="utf-8")


def load_db() -> dict:
    _init_db_if_needed()
    with DB_LOCK:
        return json.loads(DB_PATH.read_text(encoding="utf-8"))


def save_db(db: dict) -> None:
    with DB_LOCK:
        DB_PATH.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


def country_to_flag(code: Optional[str]) -> str:
    """
    'US' -> 🇺🇸
    Вернёт '' если кода нет или он не 2 буквы.
    """
    if not code or len(code) != 2:
        return ""
    return "".join(chr(ord(c.upper()) + 127397) for c in code)


def send_message(chat_id: int, text: str, reply_markup: Optional[dict] = None, parse_mode: Optional[str] = None) -> None:
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode

    # Telegram API
    r = requests.post(TG_SEND_URL, json=payload, timeout=10)
    if not r.ok:
        raise RuntimeError(f"Telegram sendMessage failed: {r.status_code} {r.text}")


# -------------------- Models --------------------

class RegisterPayload(BaseModel):
    uid: str
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None


class ConfirmPayload(BaseModel):
    uid: str
    time_local: str
    time_utc: str
    device: str
    ip: Optional[str] = None
    country: Optional[str] = None         # может быть названием страны
    country_code: Optional[str] = None    # если передашь 2-буквенный код — будет флаг
    city: Optional[str] = None
    ref: Optional[str] = None
    session: Optional[str] = None


class DecisionPayload(BaseModel):
    uid: str
    action: Literal["approve", "reject"]


# -------------------- Routes --------------------

@app.get("/")
def root():
    return {"ok": True, "service": "perplexity-contest-server"}


@app.post("/register")
def register(p: RegisterPayload):
    """
    Вызывается ботом при /start.
    Сохраняем связку uid -> telegram user_id (+ username) и выдаём номер участника.
    """
    db = load_db()
    participants = db["participants"]

    if p.uid in participants:
        rec = participants[p.uid]
        rec["user_id"] = p.user_id
        rec["username"] = p.username
        rec["first_name"] = p.first_name
    else:
        db["counter"] += 1
        rec = {
            "uid": p.uid,
            "user_id": p.user_id,
            "username": p.username,
            "first_name": p.first_name,
            "number": db["counter"],
            "status": "waiting_confirm",
            "site_data": None,
        }
        participants[p.uid] = rec

    save_db(db)
    return {"ok": True, "number": rec["number"]}


@app.options("/confirm")
def options_confirm():
    # preflight CORS
    return {"ok": True}


@app.post("/confirm")
def confirm(c: ConfirmPayload):
    """
    Вызывается сайтом при нажатии кнопки.
    1) Записываем site_data
    2) Пишем участнику сообщение №3
    3) Пишем админу карточку + inline кнопки
    """
    db = load_db()
    participants = db["participants"]
    rec = participants.get(c.uid)

    # Запишем подтверждение даже если человек не регистрировался в боте (на всякий)
    if rec:
        rec["status"] = "pending_review"
        rec["site_data"] = c.dict()
        save_db(db)

        # Сообщение участнику №3
        try:
            send_message(
                rec["user_id"],
                "Мы получили ваши данные, после сверивания вам придёт подтверждение в участии, ожидайте!"
            )
        except Exception as e:
            # не валим запрос пользователю, но админу сообщим
            if ADMIN_ID:
                send_message(ADMIN_ID, f"⚠ Не удалось написать участнику UID={c.uid}: {e}")
    else:
        # если нет регистрации — предупредим админа
        if ADMIN_ID:
            send_message(ADMIN_ID, f"⚠ Подтверждение без /start регистрации в боте.\nUID: {c.uid}")
        return {"ok": True, "warning": "uid_not_registered_in_bot"}

    # Подготовка карточки админу
    country_name = c.country or "unknown"
    code = (c.country_code or "").strip()
    if not code and c.country and len(c.country.strip()) == 2:
        code = c.country.strip()
    flag = country_to_flag(code)

    tg_line = f"@{rec['username']} " if rec.get("username") else ""
    text_admin = (
        f"Новый участник #{rec['number']}\n"
        f"UID: {c.uid}\n\n"
        f"Пользователь: {tg_line}(id {rec['user_id']})\n\n"
        f"{flag} {country_name}\n"
        f"Город: {c.city}\n"
        f"IP: {c.ip}\n"
        f"Local time: {c.time_local}\n"
        f"UTC: {c.time_utc}\n"
        f"Устройство: {c.device}"
    )

    markup = {
        "inline_keyboard": [[
            {"text": f"✅ Одобрить #{rec['number']}", "callback_data": f"approve:{c.uid}"},
            {"text": f"❌ Отклонить #{rec['number']}", "callback_data": f"reject:{c.uid}"},
        ]]
    }

    if ADMIN_ID:
        send_message(ADMIN_ID, text_admin, reply_markup=markup)

    return {"ok": True, "number": rec["number"]}


@app.post("/decision")
def decision(d: DecisionPayload):
    """
    Вызывается ботом (локально), когда админ нажал inline-кнопку.
    Сервер:
    - меняет статус
    - пишет участнику финальное сообщение
    """
    db = load_db()
    participants = db["participants"]
    rec = participants.get(d.uid)
    if not rec:
        raise HTTPException(status_code=404, detail="UID not found")

    rec["status"] = "approved" if d.action == "approve" else "rejected"
    save_db(db)

    if d.action == "approve":
        text = "Всё хорошо, вы учаавствуете в конкурсе, ожидайте результатов!"
    else:
        text = "К сожалению, вы не были допущены к участию в конкурсе."

    send_message(rec["user_id"], text)
    return {"ok": True, "uid": d.uid, "status": rec["status"], "number": rec["number"]}


@app.post("/reset")
def reset():
    """
    Сброс базы участников и нумерации (начать отсчёт заново).
    Вызывается ботом (локально) по команде /reset, либо тобой вручную.
    """
    db = {"counter": 0, "participants": {}}
    save_db(db)
    return {"ok": True}
