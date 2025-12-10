from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import httpx

# Загружаем токен и id админа из переменных окружения Railway
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

app = FastAPI()

# --- CORS, чтобы GitHub Pages мог дергать backend ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://uwezert.github.io"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# --- Модель того, что приходит с фронта ---
class ConfirmPayload(BaseModel):
    uid: str
    time_local: str
    time_utc: str
    device: str
    tz: str
    ip: str | None = None
    country: str | None = None
    city: str | None = None


# --- OPTIONS /confirm: preflight от браузера ---
@app.options("/confirm")
async def options_confirm():
    # FastAPI сам подставит CORS-заголовки
    return {"ok": True}


# --- GET /confirm: просто healthcheck ---
@app.get("/confirm")
async def get_confirm():
    return {"ok": True, "message": "GET /confirm работает"}


# --- POST /confirm: основная логика ---
@app.post("/confirm")
async def post_confirm(data: ConfirmPayload):
    text = (
        "📩 <b>Новое подтверждение</b>\n\n"
        f"UID: <code>{data.uid}</code>\n"
        f"IP: {data.ip}\n"
        f"Город: {data.city}\n"
        f"Страна: {data.country}\n\n"
        f"Local: {data.time_local}\n"
        f"UTC: {data.time_utc}\n"
        f"Device: {data.device}\n"
        f"TZ: {data.tz}"
    )

    async with httpx.AsyncClient() as client:
        await client.post(
            BOT_API,
            json={"chat_id": ADMIN_ID, "text": text, "parse_mode": "HTML"},
        )

    return {"ok": True}


# корневой "/" просто чтобы было понятно, что сервер жив
@app.get("/")
async def root():
    return {"status": "running"}

