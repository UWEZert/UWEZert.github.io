from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID  = os.getenv("ADMIN_ID")

bot_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

app = FastAPI()

# -------- CORS (важно для GitHub Pages) --------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://uwezert.github.io"],
    allow_methods=["POST"],
    allow_headers=["*"],
)


# -------- модель данных --------
class Payload(BaseModel):
    uid: str
    ip: str | None = None
    city: str | None = None
    country: str | None = None
    time_local: str | None = None
    time_utc: str | None = None
    device: str | None = None
    tz: str | None = None


# -------- POST /confirm --------
@app.post("/confirm")
async def confirm(data: Payload):

    msg = (
        "🔥 Новое подтверждение!\n\n"
        f"UID: {data.uid}\n"
        f"IP: {data.ip}\n"
        f"Город: {data.city}\n"
        f"Страна: {data.country}\n"
        f"Local time: {data.time_local}\n"
        f"UTC: {data.time_utc}\n"
        f"Устройство: {data.device}\n"
        f"TZ: {data.tz}"
    )

    # отправляем уведомление в личку администратора
    requests.post(bot_url, data={
        "chat_id": ADMIN_ID,
        "text": msg
    })

    return {"status": "ok"}
