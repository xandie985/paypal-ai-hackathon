"""One web service: the API serves the built frontend, and the run registry behaves on a long-lived server."""

import asyncio
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import runs
from app.config import Settings, settings
from app.main import app, mount_frontend
from app.orchestrator import DEMO_MANDATE, Runtime

client = TestClient(app)


def test_frontend_is_served_at_root_and_api_routes_still_win(tmp_path):
    (tmp_path / "index.html").write_text("<title>PactGuard</title>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    site = FastAPI()

    @site.get("/api/ping")
    def ping():
        return {"pong": True}

    assert mount_frontend(site, str(tmp_path)) is True
    c = TestClient(site)
    assert "PactGuard" in c.get("/").text
    assert c.get("/assets/app.js").status_code == 200
    assert c.get("/api/ping").json() == {"pong": True}
    assert c.get("/api/missing").status_code == 404


@pytest.mark.parametrize("dist", ["", "/nonexistent/dist"])
def test_nothing_is_mounted_without_a_built_frontend(dist):
    assert mount_frontend(FastAPI(), dist) is False


def test_cors_origins_come_from_settings():
    assert "http://localhost:5173" in settings.cors_origins
    r = client.options("/api/health", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    blocked = client.options("/api/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in blocked.headers


def test_the_oldest_runs_are_dropped_past_the_cap(monkeypatch):
    monkeypatch.setattr(runs, "RUNS", {})
    monkeypatch.setattr(runs, "MAX_RUNS", 3)
    ids = [client.post("/api/runs").json()["run_id"] for _ in range(5)]
    assert list(runs.RUNS) == ids[-3:]
    assert client.get(f"/api/runs/{ids[0]}").status_code == 404
    assert client.get(f"/api/runs/{ids[-1]}").status_code == 200


@pytest.mark.asyncio
async def test_events_emitted_on_a_worker_thread_reach_an_sse_subscriber():
    run = runs.Run("thread-test", Runtime.build(settings, ":memory:"), DEMO_MANDATE)
    q: asyncio.Queue = asyncio.Queue()
    run.subscribers.append((asyncio.get_running_loop(), q))
    await asyncio.to_thread(run.emit, "1", "from_a_thread")  # sync step endpoints run here
    event = await asyncio.wait_for(q.get(), timeout=2)
    assert event["event"] == "from_a_thread"


def test_gate_secret_placeholder_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="pactguard.config"):
        Settings(gate_secret="dev-only-gate-secret-change-me")
    assert any("GATE_SECRET" in r.message for r in caplog.records)

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="pactguard.config"):
        Settings(gate_secret="production-secure-random-secret-123456789")
    assert not any("GATE_SECRET" in r.message for r in caplog.records)


def test_live_mode_refuses_the_placeholder_gate_secret():
    import pytest

    with pytest.raises(ValueError, match="GATE_SECRET"):
        Settings(gate_secret="dev-only-gate-secret-change-me", replay_mode=False)
    Settings(gate_secret="production-secure-random-secret-123456789", replay_mode=False)
