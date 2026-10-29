from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_demo_endpoint_and_studio_rows():
    out = client.post("/api/demo/run").json()
    assert out["kpis"]["transactions"] == 3
    assert client.get("/api/ledger/verify").json()["chain_ok"] is True
    rows = client.get("/api/studio/rows").json()["rows"]
    assert {r["route"] for r in rows} == {"AUTO_SETTLE", "HUMAN_APPROVAL", "BLOCKED"}
