from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .config import settings

app = FastAPI(title="PactGuard AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "replay_mode": settings.replay_mode,
        "paypal_live": settings.paypal_live,
        "channel3_configured": bool(settings.channel3_api_key),
        "llm_configured": bool(settings.anthropic_api_key),
    }
