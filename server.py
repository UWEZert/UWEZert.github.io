from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from bot import process_verification

app = FastAPI()

# Разрешаем запросы с GitHub Pages
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://uwezert.github.io",
        "https://uwezert.github.io/",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/confirm")
async def confirm(request: Request):
    data = await request.json()  # строго JSON
    uid = data.get("uid")
    if not uid:
        return {"status": "error", "reason": "uid_missing"}

    await process_verification(uid, data)
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8080)
