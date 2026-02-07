# server.py
from __future__ import annotations

import os
import logging
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from db import Storage

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load .env for local development. Railway uses env vars directly, so this is safe.
load_dotenv()

DB_PATH = os.getenv("DB_PATH", "data/app.db")
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY", "")

# Comma-separated list of allowed origins for the static page
# Example: "https://uwezert.github.io   ,https://uwezert.github.io/   "
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
    # --- Логирование для отладки ---
    logger.info(f"Received POST request to /register from {req.client.host}")
    try:
        body_bytes = await req.body()
        logger.info(f"Request body (raw bytes): {body_bytes[:200]}...") # Логируем первые 200 байт тела
    except Exception as e:
        logger.error(f"Failed to read raw request body: {e}")
        # Продолжаем, так как FastAPI уже прочитал тело для валидации Pydantic
    # ------------------------------

    # Логика обработки остается прежней, но оборачиваем в try-except для отлова ошибок в storage.register
    try:
        token = await storage.register(
            uid=data.uid,
            user_id=data.user_id,
            chat_id=data.chat_id,
            username=data.username,
            first_name=data.first_name,
            last_name=data.last_name,
            ip=_client_ip(req),
        )
        logger.info(f"Registration successful for UID: {data.uid}, returning token.")
        return RegisterOut(token=token)
    except Exception as e:
        logger.error(f"Error during registration for UID {data.uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error during registration")


@app.post("/confirm")
async def confirm(req: Request, data: ConfirmIn) -> dict[str, str]:
    logger.info(f"Received POST request to /confirm from {req.client.host}")
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
            logger.warning(f"Confirm failed due to {code} for UID: {data.uid}")
            raise HTTPException(status_code=400, detail=code)
        logger.error(f"Unexpected ValueError during confirm for UID {data.uid}: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error during confirm for UID {data.uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error during confirmation")
    logger.info(f"Confirmation successful for UID: {data.uid}")
    return {"status": "ok"}


@app.get("/pending")
async def pending(limit: int = 10, _: None = Depends(require_api_key)) -> dict[str, Any]:
    logger.info(f"Received GET request to /pending with limit={limit}")
    try:
        items = await storage.pending(limit=int(limit))
        logger.info(f"Returned {len(items)} pending items.")
        return {"items": items}
    except Exception as e:
        logger.error(f"Error fetching pending items: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error fetching pending items")


@app.post("/decision")
async def decision(data: DecisionIn, _: None = Depends(require_api_key)) -> dict[str, Any]:
    logger.info(f"Received POST request to /decision for UID: {data.uid}, action: {data.action}")
    admin_id = int(data.admin_id or 0)
    if admin_id <= 0:
        # keep it optional, but encourage sending
        admin_id = -1
    try:
        p = await storage.decide(uid=data.uid, action=data.action, admin_id=admin_id, note=data.note)
        logger.info(f"Decision '{data.action}' processed for UID: {data.uid}")
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
    except ValueError as e:
        logger.warning(f"Decision failed due to {str(e)} for UID: {data.uid}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during decision for UID {data.uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error processing decision")


@app.post("/reset")
async def reset(_: None = Depends(require_api_key)) -> dict[str, str]:
    logger.info("Received POST request to /reset")
    try:
        await storage.reset()
        logger.info("Database reset completed successfully.")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error during database reset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error during reset")


if __name__ == "__main__":
    # Railway sets PORT; default for local dev.
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    # Configure CORS origins for logging
    logger.info(f"CORS origins configured: {CORS_ORIGINS}")
    if CORS_ORIGINS == ["*"]:
        logger.warning("CORS is open to all origins (*). This is insecure for production.")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)

