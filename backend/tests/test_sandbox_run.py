"""A sandbox run opts one run into the real PayPal sandbox while the deployment stays in replay."""

import pytest
from fastapi.testclient import TestClient

from app import sandbox_gate
from app.integrations.paypal import ReplayPayPal
from app.main import app, settings
from tests.test_paypal_sandbox import FakePayPal, sandbox

client = TestClient(app)


@pytest.fixture
def enabled(monkeypatch, tmp_path):
    fake = FakePayPal()
    monkeypatch.setattr(settings, "allow_sandbox_runs", True)
    monkeypatch.setattr(settings, "paypal_client_id", "cid")
    monkeypatch.setattr(settings, "paypal_client_secret", "secret")
    monkeypatch.setattr(settings, "paypal_vault_id", "vault_test_789")
    monkeypatch.setattr(settings, "ledger_path", str(tmp_path / "ledger.db"))
    monkeypatch.setattr("app.orchestrator.make_gateway", lambda s: ReplayPayPal() if s.replay_mode else sandbox(fake))
    sandbox_gate.reset()
    yield fake
    sandbox_gate.reset()


def test_refused_unless_the_server_enables_it(monkeypatch):
    monkeypatch.setattr(settings, "allow_sandbox_runs", False)
    assert client.get("/api/health").json()["sandbox_run_available"] is False
    assert client.post("/api/runs", json={"sandbox": True}).status_code == 403
    monkeypatch.setattr(settings, "allow_sandbox_runs", True)
    monkeypatch.setattr(settings, "paypal_vault_id", "")  # enabled, but no saved wallet to charge
    assert client.post("/api/runs", json={"sandbox": True}).status_code == 403


def test_sandbox_run_pays_from_the_saved_wallet_and_leaves_replay_alone(enabled):
    assert client.get("/api/health").json()["sandbox_run_available"] is True
    snap = client.post("/api/runs", json={"sandbox": True}).json()
    assert snap["sandbox"] is True and settings.replay_mode is True
    cam = next(i for i in snap["items"] if i["need"]["category"] == "webcams")
    assert cam["status"] == "settled" and cam["order_id"].startswith("5O") and cam["capture_id"].startswith("CAP")

    # A held purchase is paid from the same wallet after approval: no popup, no buyer login.
    mon = next(i for i in snap["items"] if i["need"]["category"] == "monitors")
    base = f"/api/runs/{snap['run_id']}"
    assert client.post(f"{base}/decisions/{mon['lineage_id']}/approve").status_code == 200
    assert client.post(f"{base}/orders/{mon['lineage_id']}/prepare").status_code == 200
    assert client.post(f"{base}/orders/{mon['lineage_id']}/capture").status_code == 200
    assert any(r.url.path == "/v2/checkout/orders" and b"vault_test_789" in r.content for r in enabled.requests)
    assert "vault_test_789" not in client.get(base).text + client.get(f"{base}/ledger").text  # never leaves the server

    # The next ordinary run is still replay.
    plain = client.post("/api/runs").json()
    assert plain["sandbox"] is False
    assert next(i for i in plain["items"] if i["status"] == "settled")["order_id"].startswith("ORD-REPLAY")


def test_sandbox_run_budget_is_capped(enabled):
    big = {"sandbox": True, "mandate": client.post("/api/runs").json()["mandate"] | {"budget": "999999"}}
    res = client.post("/api/runs", json=big)
    assert res.status_code == 422 and "capped" in res.text


def test_sandbox_runs_are_rate_limited_per_client_and_overall(enabled, monkeypatch):
    for _ in range(sandbox_gate.PER_CLIENT):
        assert client.post("/api/runs", json={"sandbox": True}).status_code == 200
    assert client.post("/api/runs", json={"sandbox": True}).status_code == 429
    # Another client has its own allowance, but the overall ceiling still applies.
    assert sandbox_gate.allow("other", global_limit=100) is True
    assert sandbox_gate.allow("third", global_limit=sandbox_gate.PER_CLIENT + 1) is False


def test_the_window_slides():
    sandbox_gate.reset()
    for i in range(sandbox_gate.PER_CLIENT):
        assert sandbox_gate.allow("a", 100, now=1000.0 + i)
    assert not sandbox_gate.allow("a", 100, now=1010.0)
    assert sandbox_gate.allow("a", 100, now=1000.0 + sandbox_gate.WINDOW_S + 5)
    sandbox_gate.reset()


def test_reconciliation_calls_a_real_sandbox_capture_what_it_is(enabled):
    snap = client.post("/api/runs", json={"sandbox": True}).json()
    cam = next(i for i in snap["items"] if i["need"]["category"] == "webcams")
    rows = client.get("/api/studio/reconciliation", params={"run_id": snap["run_id"], "fixture": "true"}).json()["rows"]
    mine = next(r for r in rows if r["id"] == cam["capture_id"])
    assert mine["status"] == "Sandbox capture"
    assert all(r["status"] != "Sandbox capture" for r in rows if r["origin"] == "seeded")
