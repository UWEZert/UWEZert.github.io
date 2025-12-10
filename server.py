from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

app = FastAPI()

# Разрешаем запросы с твоего GitHub Pages
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://uwezert.github.io"],
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

class Payload(BaseModel):
    uid: str
    ip: str | None = None
    city: str | None = None
    country: str | None = None
    time_local: str | None = None
    time_utc: str | None = None
    device: str | None = None
    tz: str | None = None

@app.post("/confirm")
async def confirm(data: Payload):
    message = (
        f"Новое подтверждение:\n"
        f"UID: {data.uid}\n"
        f"Город: {data.city}\n"
        f"Страна: {data.country}\n"
        f"Время (local): {data.time_local}\n"
        f"Время (UTC): {data.time_utc}"
    )

    requests.post(
        CHAT_ID_URL,
        data={
            "chat_id": os.getenv("ADMIN_ID"),
            "text": message
        }
    )

    return {"status": "ok"}
