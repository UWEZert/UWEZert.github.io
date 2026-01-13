# server.py
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx # Добавлен
import asyncio # Добавлен

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --- ИМПОРТ STORAGE ТЕПЕРЬ ОБЯЗАТЕЛЕН ---
from db import Storage # Импортируем Storage

# --- Настройка логирования ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load .env for local development. Railway uses env vars directly, so this is safe.
load_dotenv()

DB_PATH = os.getenv("DB_PATH", "data/app.db")
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY", "")

# Comma-separated list of allowed origins for the static page
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
logger.info(f"CORS origins configured: {CORS_ORIGINS}")

app = FastAPI(title="UWEZert Verification Backend")

if CORS_ORIGINS == ["*"]:
    logger.warning("CORS is open to all origins (*). This is insecure for production.")
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

# --- ИНИЦИАЛИЗАЦИЯ STORAGE ---
storage = Storage(DB_PATH)

def _client_ip(req: Request) -> Optional[str]:
    xff = req.headers.get("x-forwarded-for")
    if xff:
        ip = xff.split(",")[0].strip()
        logger.debug(f"Client IP determined from X-Forwarded-For: {ip}")
        return ip
    ip = req.client.host if req.client else None
    logger.debug(f"Client IP determined from request.client: {ip}")
    return ip

# --- Функция геолокации по IP ---
GEO_IP_TIMEOUT = 5.0
GEO_IP_PROVIDER = "ip-api.com" # Вы можете выбрать другой

async def get_geo_data_from_ip(ip_address: str) -> Optional[dict[str, Any]]:
    """Получает геоданные по IP-адресу."""
    if not ip_address or ip_address in ['127.0.0.1', '::1']:
         logger.warning(f"Skipping geo lookup for local IP: {ip_address}")
         return None

    url = f"http://{GEO_IP_PROVIDER}/json/{ip_address}"

    try:
        async with httpx.AsyncClient(timeout=GEO_IP_TIMEOUT) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            if data.get('status') == 'success':
                 geo_result = {
                     "ip_resolved_location": {
                         "query": data.get('query'),
                         "country": data.get('country'),
                         "region": data.get('regionName'),
                         "city": data.get('city'),
                         "lat": data.get('lat'),
                         "lon": data.get('lon'),
                         "timezone": data.get('timezone'),
                         "isp": data.get('isp'),
                         "org": data.get('org'),
                     }
                 }
                 logger.info(f"Geo data fetched for IP {ip_address}: {geo_result['ip_resolved_location'].get('city')}, {geo_result['ip_resolved_location'].get('country')}")
                 return geo_result
            else:
                 logger.warning(f"Geo API returned non-success status for IP {ip_address}: {data.get('status', 'unknown_status')}, message: {data.get('message', 'no_message')}")
                 return None

    except httpx.TimeoutException:
        logger.error(f"Timeout while fetching geo data for IP {ip_address}")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error {e.response.status_code} from Geo API for IP {ip_address}: {e}")
    except httpx.RequestError as e:
        logger.error(f"Request error to Geo API for IP {ip_address}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during geo lookup for IP {ip_address}: {e}")

    return None

async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    logger.debug(f"Validating API key in header: {x_api_key is not None}")
    if not BACKEND_API_KEY:
        logger.error("BACKEND_API_KEY not set on the server!")
        raise HTTPException(status_code=500, detail="BACKEND_API_KEY not set")
    if not x_api_key or x_api_key != BACKEND_API_KEY:
        logger.warning(f"Unauthorized access attempt with key: {x_api_key}")
        raise HTTPException(status_code=401, detail="unauthorized")
    logger.debug("API key validation successful")

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
    payload: dict[str, Any] = Field(default_factory=dict)

class DecisionIn(BaseModel):
    uid: str
    action: str = Field(..., pattern="^(approve|reject)$")
    note: Optional[str] = None
    admin_id: Optional[int] = None

class CreateContestIn(BaseModel):
    name: str

class CreateContestOut(BaseModel):
    contest_id: int

@app.get("/health")
async def health() -> dict[str, str]:
    logger.info("Health check endpoint called")
    await storage.init() # Инициализация storage при первом запросе
    logger.info("Health check passed")
    return {"status": "ok"}

@app.post("/register", response_model=RegisterOut)
async def register(req: Request, data: RegisterIn) -> RegisterOut:
    ip = _client_ip(req)
    logger.info(f"Registration request for UID {data.uid} from IP {ip}")

    token = await storage.register(
        uid=data.uid,
        user_id=data.user_id,
        chat_id=data.chat_id,
        username=data.username,
        first_name=data.first_name,
        last_name=data.last_name,
        ip=ip,
    )
    logger.info(f"Registration successful for UID {data.uid}")
    return RegisterOut(token=token)

@app.post("/confirm")
async def confirm(req: Request, data: ConfirmIn) -> dict[str, str]:
    ip = _client_ip(req)
    user_agent = req.headers.get("user-agent")
    logger.info(f"Confirmation request for UID {data.uid} from IP {ip}")

    # --- ШАГ 1: Получить геоданные по IP ---
    geo_data = await get_geo_data_from_ip(ip)
    if not geo_data: # --- ИСПРАВЛЕНО: добавлено 'data' и двоеточие ---
        # --- КРИТИЧЕСКОЕ ИЗМЕНЕНИЕ ---
        logger.warning(f"Failed to resolve location for IP {ip} during confirmation for UID {data.uid}. Returning error to client.")
        raise HTTPException(status_code=400, detail="location_resolution_failed")

    # --- ШАГ 2: Добавить геоданные к payload ---
    data.payload.update(geo_data)
    logger.debug(f"Final payload with geo data for UID {data.uid}")

    try:
        await storage.confirm(
            uid=data.uid,
            token=data.token,
            payload=data.payload,
            ip=ip,
            user_agent=user_agent,
        )
        logger.info(f"Confirmation successful for UID {data.uid}, including geo data.")
        # --- УБРАНО: Вызов notify_admin --- Сервер больше не отправляет уведомления

    except ValueError as e:
        code = str(e)
        logger.warning(f"Confirmation failed for UID {data.uid} due to: {code}")
        if code in ("unknown_uid", "bad_token"):
            raise HTTPException(status_code=400, detail=code)
        raise
    except Exception as e:
        logger.error(f"Unexpected error during confirmation for UID {data.uid}: {e}")
        raise HTTPException(status_code=500, detail="internal_error")

    return {"status": "ok_with_geo"}

# --- НОВЫЙ ЭНДПОИНТ ДЛЯ БОТА (API POLLING) ---
@app.get("/new_confirmations_for_admin")
async def get_new_confirmations_for_admin(_: None = Depends(require_api_key)) -> dict[str, Any]:
    """
    Возвращает список новых подтверждений для администратора, включая геоданные.
    Используется ботом для опроса (polling) новых участников.
    """
    logger.info("New confirmations endpoint called by admin bot.")
    items = await storage.pending(limit=50)
    enhanced_items = []

    for item in items:
        uid = item["uid"]
        # Получаем последний сабмит для извлечения geo_data
        last_submission_info = await storage.get_last_submission_info(uid)
        geo_data = last_submission_info.get("payload_json", {}).get("ip_resolved_location", {}) if last_submission_info else {}
        # Добавляем geo_data к item
        enhanced_item = item.copy()
        enhanced_item['submission_payload'] = last_submission_info.get("payload_json", {}) if last_submission_info else {}
        enhanced_items.append(enhanced_item)

    logger.info(f"Returning {len(enhanced_items)} confirmations awaiting admin review via API with geo data.")
    return {"items": enhanced_items}

@app.get("/pending") # Опционально, если используется как резерв
async def pending(limit: int = 10, _: None = Depends(require_api_key)) -> dict[str, Any]:
    logger.info(f"Pending list requested with limit {limit}")
    items = await storage.pending(limit=int(limit))
    logger.info(f"Returning {len(items)} pending items")
    return {"items": items}

@app.post("/decision")
async def decision(data: DecisionIn, _: None = Depends(require_api_key)) -> dict[str, Any]:
    admin_id = int(data.admin_id or 0)
    if admin_id <= 0:
        admin_id = -1
    logger.info(f"Decision request received for UID {data.uid} by admin {admin_id}, action: {data.action}")

    try:
        p = await storage.decide(uid=data.uid, action=data.action, admin_id=admin_id, note=data.note)
        logger.info(f"Decision '{data.action}' applied successfully for UID {data.uid}")
    except ValueError as e:
        logger.error(f"Decision failed for UID {data.uid} due to invalid UID: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during decision for UID {data.uid}: {e}")
        raise HTTPException(status_code=500, detail="internal_error")

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
            "contest_id": p.contest_id,
        },
    }

@app.post("/reset")
async def reset(_: None = Depends(require_api_key)) -> dict[str, str]:
    logger.info("Reset command received via API")
    await storage.reset()
    logger.info("Database reset completed")
    return {"status": "ok"}

# --- НОВЫЕ ЭНДПОИНТЫ ДЛЯ АДМИНИСТРАТИВНЫХ КОМАНД БОТА ---
@app.post("/create_contest", response_model=CreateContestOut)
async def create_contest_api(data: CreateContestIn, _: None = Depends(require_api_key)) -> CreateContestOut:
    name = data.name or f"Contest_{utc_now_iso()}"
    contest_id = await storage.create_contest(name)
    logger.info(f"Contest '{name}' (ID: {contest_id}) created via API.")
    return CreateContestOut(contest_id=contest_id)

@app.get("/list_contests")
async def list_contests_api(_: None = Depends(require_api_key)) -> dict[str, Any]:
    contests = await storage.get_all_contests()
    logger.info(f"Fetched {len(contests)} contests via API.")
    return {"contests": contests}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"Starting server on port {port}")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
