import os
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# ====== настройки ======
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
SUBMISSIONS_FILE = DATA_DIR / "submissions.jsonl"
# =======================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"ok": True, "service": "confirm-api"}

@app.get("/health")
async def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}

@app.post("/confirm")
async def confirm(request: Request):
    
    payload: Dict[str, Any] = await request.json()

    # Минимальная проверка
    uid = payload.get("uid")
    if not uid:
        return {"ok": False, "error": "uid_missing"}

    payload["_received_at_utc"] = datetime.utcnow().isoformat()

    
    with SUBMISSIONS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    return {"ok": True}
