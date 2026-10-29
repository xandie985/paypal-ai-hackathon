from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings

app = FastAPI(title="PactGuard AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "paypal_configured": bool(settings.paypal_client_id),
        "channel3_configured": bool(settings.channel3_api_key),
        "replay_mode": settings.replay_mode,
    }
