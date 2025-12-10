from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")  # твой Telegram ID
BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

app = FastAPI()

# --------- FIX: Разрешаем CORS + OPTIONS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------- Модель данных ----------
class ConfirmPayload(BaseModel):
    uid: str
    time_local: str
    time_utc: str
    device: str
    tz: str
    ip: str | None = None
    country: str | None = None
    city: str | None = None

# --------- OPTIONS Хэндлер (ОБЯЗАТЕЛЬНО) ----------
@app.options("/confirm")
async def options_handler():
    return {"status": "ok"}

# --------- POST /confirm ----------
@app.post("/confirm")
async def confirm(data: ConfirmPayload):

    text = (
        "📩 <b>Получено подтверждение с сайта</b>\n\n"
        f"UID: <code>{data.uid}</code>\n"
        f"🌍 IP: {data.ip}\n"
        f"🏙 Город: {data.city}\n"
        f"🌐 Страна: {data.country}\n\n"
        f"🕒 Local: {data.time_local}\n"
        f"🕒 UTC: {data.time_utc}\n"
        f"💻 Device: {data.device}\n"
        f"⏱ TZ: {data.tz}"
    )

    # отправляем админу
    async with httpx.AsyncClient() as client:
        await client.post(
            BOT_API,
            json={"chat_id": ADMIN_ID, "text": text, "parse_mode": "HTML"}
        )

    return {"ok": True}

# --------- healthcheck ----------
@app.get("/")
async def root():
    return {"status": "running"}
