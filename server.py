from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import os
import base64

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],      
    allow_headers=["*"],
)

class Payload(BaseModel):
    uid: str
    time_local: str
    time_utc: str
    device: str
    ip: str
    country: str
    city: str
    ref: str
    session: str


@app.post("/confirm")
async def confirm(data: Payload):
    """Принимаем JSON от фронта"""
    encoded = base64.b64encode(data.json().encode()).decode()
    return {"ok": True, "encoded": encoded}


@app.options("/confirm")
async def options_confirm():
    return {"ok": True}
