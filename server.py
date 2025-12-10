import os
import json
from pathlib import Path
from typing import Optional, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

DB_PATH = Path("participants.json")

app = FastAPI()

# Разрешаем запросы с GitHub Pages
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://uwezert.github.io"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def load_db():
    if not DB_PATH.exists():
        return {"counter": 0, "participants": {}}
    with DB_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_db(db):
    with DB_PATH.open("w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


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
    country: Optional[str] = None
    city: Optional[str] = None
    ref: Optional[str] = None
    session: Optional[str] = None


class DecisionPayload(BaseModel):
    uid: str
    action: Literal["approve", "reject"]


@app.get("/")
async def root():
    return {"status": "running"}


@app.post("/register")
async def register(p: RegisterPayload):
    """
    Вызывается ботом при /start — регистрируем пользователя и выдаём номер участника.
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
async def options_confirm():
    # preflight CORS
    return {"ok": True}


@app.post("/confirm")
async def confirm(c: ConfirmPayload):
    """
    Вызывается сайтом при нажатии кнопки "Подтвердить участие".
    """
    db = load_db()
    participants = db["participants"]
    rec = participants.get(c.uid)

    if rec:
        rec["status"] = "pending_review"
        rec["site_data"] = c.dict()
        save_db(db)

    async with httpx.AsyncClient() as client:
        # Сообщение участнику
        if rec:
            text_user = (
                "Мы получили ваши данные, после сверивания вам придёт подтверждение "
                "в участии, ожидайте!"
            )
            await client.post(
                f"{TELEGRAM_API}/sendMessage",
                json={"chat_id": rec["user_id"], "text": text_user},
            )

        # Сообщение админу
        lines = []
        if rec:
            lines.append(f"Новый участник #{rec['number']}")
            lines.append(f"UID: {c.uid}")
            uline = "Пользователь: "
            if rec.get("username"):
                uline += f"@{rec['username']} "
            uline += f"(id {rec['user_id']})"
            lines.append(uline)
        else:
            lines.append("⚠ Подтверждение без регистрации в боте!")
            lines.append(f"UID: {c.uid}")

        lines.append("")
        lines.append(f"Страна: {c.country}")
        lines.append(f"Город: {c.city}")
        lines.append(f"IP: {c.ip}")
        lines.append(f"Local time: {c.time_local}")
        lines.append(f"UTC: {c.time_utc}")
        lines.append(f"Устройство: {c.device}")
        text_admin = "\n".join(lines)

        reply_markup = None
        if rec:
            reply_markup = {
                "inline_keyboard": [[
                    {"text": f"✅ Одобрить #{rec['number']}",
                     "callback_data": f"approve:{c.uid}"},
                    {"text": f"❌ Отклонить #{rec['number']}",
                     "callback_data": f"reject:{c.uid}"},
                ]]
            }

        await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": ADMIN_ID,
                "text": text_admin,
                "reply_markup": reply_markup,
            },
        )

    return {"ok": True}


@app.post("/decision")
async def decision(d: DecisionPayload):
    """
    Вызывается ботом, когда админ нажимает кнопку "Одобрить/Отклонить".
    """
    db = load_db()
    participants = db["participants"]
    rec = participants.get(d.uid)
    if not rec:
        raise HTTPException(status_code=404, detail="UID not found")

    rec["status"] = "approved" if d.action == "approve" else "rejected"
    save_db(db)

    async with httpx.AsyncClient() as client:
        if d.action == "approve":
            text = "Всё хорошо, вы участвуете в конкурсе, ожидайте результатов!"
        else:
            text = "К сожалению, вы не были допущены к участию в конкурсе."

        await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": rec["user_id"], "text": text},
        )

    return {
        "ok": True,
        "status": rec["status"],
        "number": rec["number"],
        "uid": d.uid,
    }


@app.post("/reset")
async def reset():
    """
    Полный сброс списка участников и нумерации.
    """
    db = {"counter": 0, "participants": {}}
    save_db(db)
    return {"ok": True}
