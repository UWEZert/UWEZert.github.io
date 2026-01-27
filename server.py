# server.py
from __future__ import annotations

import os
import logging
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Импорт Storage закомментирован, так как мы его не используем в /register
# from db import Storage

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load .env for local development. Railway uses env vars directly, so this is safe.
load_dotenv()

# Эти переменные пока не используются в упрощённом /register
# DB_PATH = os.getenv("DB_PATH", "data/app.db")
# BACKEND_API_KEY = os.getenv("BACKEND_API_KEY", "")

# Comma-separated list of allowed origins for the static page
# Example: "https://uwezert.github.io ,https://uwezert.github.io/ "
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

app = FastAPI(title="UWEZert Verification Backend (Simplified Register)")

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

# storage = Storage(DB_PATH) # Закомментировано

# Функция _client_ip и require_api_key остаются, но не используются в упрощённом /register
def _client_ip(req: Request) -> Optional[str]:
    # Railway sits behind a proxy; X-Forwarded-For is typically set.
    xff = req.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return req.client.host if req.client else None


async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    BACKEND_API_KEY = os.getenv("BACKEND_API_KEY", "")
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
    # storage.init() # Не вызываем, так как storage не используется
    return {"status": "ok"}


@app.post("/register", response_model=RegisterOut)
async def register(req: Request, data: RegisterIn) -> RegisterOut:
    # --- Логирование получения запроса ---
    logger.info(f"Received POST request to /register from {req.client.host}")
    logger.info(f"Request data received (will be ignored): {data.dict()}")
    # --------------------------------------

    # Всегда возвращаем один и тот же тестовый токен
    test_token = "test_token_12345"
    logger.info(f"Returning fixed test token: {test_token}")
    return RegisterOut(token=test_token)


# Остальные эндпоинты (confirm, pending, decision, reset) оставим как есть,
# но они будут вызывать ошибку, так как storage не инициализирован.
# Если бот их не вызывает, это не страшно для теста /register.
# Если вызывает - можно аналогично упростить или закомментировать.

@app.post("/confirm")
async def confirm(req: Request, data: ConfirmIn) -> dict[str, str]:
    logger.info(f"Received POST request to /confirm from {req.client.host} (SKIPPED FOR TEST)")
    # Заглушка, чтобы не было ошибки, если бот случайно вызовет /confirm
    # В реальной ситуации его нужно будет раскомментировать и исправить
    # try:
    #     await storage.confirm(...)
    # except ValueError as e: ...
    return {"status": "ok (SIMULATED FOR TEST)"}

@app.get("/pending")
async def pending(limit: int = 10, _: None = Depends(require_api_key)) -> dict[str, Any]:
    logger.info(f"Received GET request to /pending (SKIPPED FOR TEST)")
    return {"items": []} # Заглушка

@app.post("/decision")
async def decision(data: DecisionIn, _: None = Depends(require_api_key)) -> dict[str, Any]:
    logger.info(f"Received POST request to /decision (SKIPPED FOR TEST)")
    # Заглушка
    return {"status": "ok", "participant": {}} # Заглушка

@app.post("/reset")
async def reset(_: None = Depends(require_api_key)) -> dict[str, str]:
    logger.info("Received POST request to /reset (SKIPPED FOR TEST)")
    return {"status": "ok (SIMULATED FOR TEST)"}


if __name__ == "__main__":
    # Railway sets PORT; default for local dev.
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    # Configure CORS origins for logging
    logger.info(f"CORS origins configured: {CORS_ORIGINS}")
    if CORS_ORIGINS == ["*"]:
        logger.warning("CORS is open to all origins (*). This is insecure for production.")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
