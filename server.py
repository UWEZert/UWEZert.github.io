from fastapi import FastAPI
from pydantic import BaseModel
import requests
import os

from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID_URL = "https://api.telegram.org/bot{}/sendMessage".format(BOT_TOKEN)

app = FastAPI()

class Payload(BaseModel):
    uid: str
    ip: str = None
    city: str = None
    country: str = None
    time_local: str = None
    time_utc: str = None
    device: str = None
    tz: str = None

@app.post("/confirm")
async def confirm(data: Payload):
    message = f"Новое подтверждение:\nUID: {data.uid}\nГород: {data.city}\nСтрана: {data.country}\nВремя: {data.time_local}"
    # Отправляем UID твоему боту
    requests.post(
        CHAT_ID_URL,
        data={
            "chat_id": os.getenv("ADMIN_ID"),
            "text": message
        }
    )
    return {"status": "ok"}
