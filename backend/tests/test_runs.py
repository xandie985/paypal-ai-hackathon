"""Run-session API: the approval pause, 409 guards, idempotent retry, SSE order, no tokens on the wire."""

import json

import pytest
from fastapi.testclient import TestClient

from app import runs
from app.main import app

client = TestClient(app)


@pytest.fixture
def run():
    snap = client.post("/api/runs").json()
    return snap, {i["need"]["category"]: i for i in snap["items"]}


def test_run_pauses_at_human_approval_and_resumes_on_approve(run):
    snap, items = run
    cam, mon = items["webcams"], items["monitors"]
    assert cam["decision"]["route"] == "AUTO_SETTLE" and cam["status"] == "settled"  # replay auto-settles small buys
    assert mon["decision"]["route"] == "HUMAN_APPROVAL" and mon["status"] == "awaiting_approval"
    assert not snap["complete"]
    base = f"/api/runs/{snap['run_id']}"
    # No approval, no order.
    assert client.post(f"{base}/orders/{mon['lineage_id']}/prepare").status_code == 409
    assert client.post(f"{base}/decisions/{mon['lineage_id']}/approve").status_code == 200
    order = client.post(f"{base}/orders/{mon['lineage_id']}/prepare").json()
    assert order["order_id"]
    cap = client.post(f"{base}/orders/{mon['lineage_id']}/capture").json()
    assert cap["status"] == "COMPLETED"
    assert client.get(base).json()["complete"] is True


def test_blocked_decision_cannot_be_approved_via_api(run):
    snap, items = run
    base = f"/api/runs/{snap['run_id']}"
    blocked = runs.RUNS[snap["run_id"]]
    # Force a BLOCKED item by running the attack proposal through the same run state.
    d = runs.step_attack(blocked)
    assert d.route == "BLOCKED"
    r = client.post(f"{base}/decisions/{d.lineage_id}/approve")
    assert r.status_code == 404  # attack proposals never become orderable items
    # And an already-authorized item can't be approved a second time.
    cam = items["webcams"]
    assert client.post(f"{base}/decisions/{cam['lineage_id']}/approve").status_code == 409


def test_blocked_vendor_is_never_orderable():
    mandate = json.loads(client.post("/api/runs").text)["mandate"]
    mandate["allowed_categories"] = ["webcams"]  # monitors are now outside the warrant
    snap = client.post(
        "/api/runs",
        json={
            "mandate": mandate,
            "needs": [{"description": "27in 4K monitor", "category": "monitors", "quantity": 3, "method": "negotiate"}],
        },
    ).json()
    item = snap["items"][0]
    assert item["decision"]["route"] == "BLOCKED"
    base = f"/api/runs/{snap['run_id']}"
    assert client.post(f"{base}/decisions/{item['lineage_id']}/approve").status_code == 409
    assert client.post(f"{base}/orders/{item['lineage_id']}/prepare").status_code == 409


def test_retry_endpoint_returns_same_order_id(run):
    snap, items = run
    cam = items["webcams"]
    r = client.post(f"/api/runs/{snap['run_id']}/orders/{cam['lineage_id']}/retry").json()
    assert r["same_order"] is True and r["order_id"] == cam["order_id"]


def test_attack_endpoint_is_blocked_fast(run):
    snap, _ = run
    r = client.post(f"/api/runs/{snap['run_id']}/attack").json()
    assert r["route"] == "BLOCKED" and r["latency_ms"] < 50


def test_approval_token_never_in_api_responses(run):
    snap, items = run
    mon = items["monitors"]
    base = f"/api/runs/{snap['run_id']}"
    client.post(f"{base}/decisions/{mon['lineage_id']}/approve")
    token = runs.RUNS[snap["run_id"]].items[mon["lineage_id"]].token
    assert token
    bodies = [client.get(base).text, client.get(f"{base}/events?follow=false").text]
    assert all(token not in b for b in bodies)


def test_events_stream_in_loop_order(run):
    snap, _ = run
    text = client.get(f"/api/runs/{snap['run_id']}/events?follow=false").text
    events = [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]
    assert [e["seq"] for e in events] == list(range(len(events)))
    assert events[0]["stage"] == "1"
    by_lineage: dict[str, list[str]] = {}
    for e in events:
        if "lineage_id" in e and e["stage"] in "234":
            by_lineage.setdefault(e["lineage_id"], []).append(e["stage"])
    assert all(v == sorted(v) for v in by_lineage.values())


def test_reject_closes_the_item(run):
    snap, items = run
    mon = items["monitors"]
    base = f"/api/runs/{snap['run_id']}"
    assert client.post(f"{base}/decisions/{mon['lineage_id']}/reject", json={"reason": "too pricey"}).status_code == 200
    assert client.post(f"{base}/orders/{mon['lineage_id']}/prepare").status_code == 409
    assert client.get(base).json()["complete"] is True
