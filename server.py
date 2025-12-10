from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import json
from pathlib import Path
import os
from dotenv import load_dotenv
import requests

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = Path("participants.json")
if not DATA_FILE.exists():
    DATA_FILE.write_text("{}", encoding="utf-8")


def load_db():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {}


def save_db(db):
    DATA_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


def country_to_flag(country_code: str | None) -> str:
    """
    Превращает код страны 'US' → '🇺🇸'.
    Если код пустой — возвращает пустую строку.
    """
    if not country_code or len(country_code) != 2:
        return ""
    return "".join(chr(ord(c.upper()) + 127397) for c in country_code)


def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(url, json=payload)


@app.post("/confirm")
async def confirm(request: Request):
    db = load_db()
    payload = await request.json()

    uid = payload.get("uid")
    if not uid:
        return {"status": "error", "reason": "UID missing"}

    # Если UID не зарегистрирован ботом
    if uid not in db:
        # Добавляем запись "без регистрации"
        db[uid] = {
            "user_id": None,
            "username": None,
            "status": "site_confirm_only",
            "number": None,
            "site": payload,
        }
        save_db(db)
        send_message(ADMIN_ID, f"⚠ Подтверждение без регистрации в боте!\nUID: {uid}")
        return {"status": "ok"}

    # Если UID найден — обновляем данные участника
    record = db[uid]
    record["site"] = payload
    record["status"] = "pending"

    # Если номер отсутствует — присваиваем
    if record.get("number") is None:
        used_numbers = [v.get("number") for v in db.values() if v.get("number")]
        next_num = max(used_numbers) + 1 if used_numbers else 1
        record["number"] = next_num

    save_db(db)

    # 1️⃣ Сообщение участнику
    user_id = record["user_id"]
    if user_id:
        send_message(user_id, "Мы получили ваши данные, после сверивания вам придёт подтверждение в участии, ожидайте!")

    # 2️⃣ Сообщение админу
    site = payload
    country = site.get("country") or "??"
    flag = country_to_flag(country)
    city = site.get("city", "?")
    ip = site.get("ip", "?")
    t_local = site.get("time_local", "?")
    t_utc = site.get("time_utc", "?")
    device = site.get("device", "?")

    username = record.get("username")
    tgline = f"@{username}" if username else "(username hidden)"

    text_admin = (
        f"Новый участник #{record['number']}\n"
        f"UID: {uid}\n\n"
        f"Пользователь: {tgline} (id {record['user_id']})\n\n"
        f"{flag} {country}\n"
        f"Город: {city}\n"
        f"IP: {ip}\n"
        f"Local time: {t_local}\n"
        f"UTC: {t_utc}\n"
        f"Устройство: {device}"
    )

    # Inline-кнопки "Одобрить / Отклонить"
    markup = {
        "inline_keyboard": [
            [
                {"text": "Одобрить", "callback_data": f"approve:{uid}"},
                {"text": "Отклонить", "callback_data": f"reject:{uid}"},
            ]
        ]
    }

    send_message(ADMIN_ID, text_admin, reply_markup=markup)

    return {"status": "ok"}
