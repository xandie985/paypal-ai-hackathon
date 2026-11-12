from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .ai_proxy import router as ai_router
from .api import router
from .config import settings
from .studio_paypal import router as studio_paypal_router
from .studio_reconcile import router as studio_reconcile_router

app = FastAPI(title="PactGuard AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(ai_router)
app.include_router(studio_paypal_router)
app.include_router(studio_reconcile_router)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "replay_mode": settings.replay_mode,
        "paypal_live": settings.paypal_live,
        "sandbox_run_available": settings.sandbox_runs_available,
        # Public by design: the JS SDK loads with it in the browser. The secret never leaves the server.
        "paypal_client_id": settings.paypal_client_id if settings.paypal_live else None,
        "currency": "USD",
        "channel3_configured": bool(settings.channel3_api_key),
        "llm_configured": bool(settings.anthropic_api_key),
    }


def mount_frontend(application: FastAPI, dist: str) -> bool:
    """Serve the built frontend at "/" so one web service hosts both. Mounted after every /api route, so those
    win. The UI routes with the URL hash, so no history fallback is needed."""
    if not dist or not (Path(dist) / "index.html").is_file():
        return False
    application.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return True


mount_frontend(app, settings.frontend_dist)
