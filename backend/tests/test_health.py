from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_demo_endpoint_and_studio_rows():
    from app import runs

    runs.RUNS.clear()  # without a run_id, Studio shows the latest run; with none, the /demo/run ledger
    out = client.post("/api/demo/run").json()
    assert out["kpis"]["transactions"] == 3
    assert client.get("/api/ledger/verify").json()["chain_ok"] is True
    rows = client.get("/api/studio/rows").json()["rows"]
    assert {r["route"] for r in rows} == {"AUTO_SETTLE", "HUMAN_APPROVAL", "BLOCKED"}
