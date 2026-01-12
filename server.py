from __future__ import annotations

import os
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from db import Storage

# Load .env for local development. Railway uses env vars directly, so this is safe.
load_dotenv()

DB_PATH = os.getenv("DB_PATH", "data/app.db")
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY", "")

# Comma-separated list of allowed origins for the static page
# Example: "https://uwezert.github.io,https://uwezert.github.io/"
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

app = FastAPI(title="UWEZert Verification Backend")

if CORS_ORIGINS == ["*"]:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

storage = Storage(DB_PATH)


def _client_ip(req: Request) -> Optional[str]:
    # Railway sits behind a proxy; X-Forwarded-For is typically set.
    xff = req.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return req.client.host if req.client else None


async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    if not BACKEND_API_KEY:
        raise HTTPException(status_code=500, detail="BACKEND_API_KEY not set")
    if not x_api_key or x_api_key != BACKEND_API_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")


class RegisterIn(BaseModel):
    uid: str = Field(..., min_length=6)
    user_id: int
    chat_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class RegisterOut(BaseModel):
    token: str


class ConfirmIn(BaseModel):
    uid: str
    token: str
    # Free-form payload from the browser (geo/time/userAgent/etc.)
    payload: dict[str, Any] = Field(default_factory=dict)


class DecisionIn(BaseModel):
    uid: str
    action: str = Field(..., pattern="^(approve|reject)$")
    note: Optional[str] = None
    admin_id: Optional[int] = None


@app.get("/health")
async def health() -> dict[str, str]:
    await storage.init()
    return {"status": "ok"}


@app.post("/register", response_model=RegisterOut)
async def register(req: Request, data: RegisterIn) -> RegisterOut:
    token = await storage.register(
        uid=data.uid,
        user_id=data.user_id,
        chat_id=data.chat_id,
        username=data.username,
        first_name=data.first_name,
        last_name=data.last_name,
        ip=_client_ip(req),
    )
    return RegisterOut(token=token)


@app.post("/confirm")
async def confirm(req: Request, data: ConfirmIn) -> dict[str, str]:
    try:
        await storage.confirm(
            uid=data.uid,
            token=data.token,
            payload=data.payload,
            ip=_client_ip(req),
            user_agent=req.headers.get("user-agent"),
        )
    except ValueError as e:
        code = str(e)
        if code in ("unknown_uid", "bad_token"):
            raise HTTPException(status_code=400, detail=code)
        raise
    return {"status": "ok"}


@app.get("/pending")
async def pending(limit: int = 10, _: None = Depends(require_api_key)) -> dict[str, Any]:
    items = await storage.pending(limit=int(limit))
    return {"items": items}


@app.post("/decision")
async def decision(data: DecisionIn, _: None = Depends(require_api_key)) -> dict[str, Any]:
    admin_id = int(data.admin_id or 0)
    if admin_id <= 0:
        # keep it optional, but encourage sending
        admin_id = -1
    try:
        p = await storage.decide(uid=data.uid, action=data.action, admin_id=admin_id, note=data.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "status": "ok",
        "participant": {
            "uid": p.uid,
            "user_id": p.user_id,
            "chat_id": p.chat_id,
            "username": p.username,
            "first_name": p.first_name,
            "last_name": p.last_name,
            "status": p.status,
            "decision": p.decision,
            "decided_at": p.decided_at,
            "decision_note": p.decision_note,
        },
    }


@app.post("/reset")
async def reset(_: None = Depends(require_api_key)) -> dict[str, str]:
    await storage.reset()
    return {"status": "ok"}


if __name__ == "__main__":
    # Railway sets PORT; default for local dev.
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
