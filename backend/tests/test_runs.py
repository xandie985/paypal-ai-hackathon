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
    cam, mon, mic = items["webcams"], items["monitors"], items["microphones"]
    assert cam["decision"]["route"] == "AUTO_SETTLE" and cam["status"] == "settled"  # replay auto-settles small buys
    assert mon["decision"]["route"] == "HUMAN_APPROVAL" and mon["status"] == "awaiting_approval"
    assert not snap["complete"]
    base = f"/api/runs/{snap['run_id']}"
    assert client.post(f"{base}/decisions/{mic['lineage_id']}/reject", json={"reason": "terms hidden"}).status_code == 200
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
    assert client.get(base).json()["complete"] is False  # the microphone is still waiting on a human
    client.post(f"{base}/decisions/{items['microphones']['lineage_id']}/reject", json={"reason": "terms hidden"})
    assert client.get(base).json()["complete"] is True


def test_hidden_return_terms_escalate_to_a_human(run):
    """arXiv:2610.17378: an agent can't decide on terms it can't see, so a cheap buy still goes to a human."""
    _, items = run
    mic = items["microphones"]
    assert mic["return_days"] is None and mic["status"] == "awaiting_approval"
    assert mic["decision"]["route"] == "HUMAN_APPROVAL"
    rev = next(f for f in mic["decision"]["factors"] if f["name"] == "reversibility")
    assert rev["passed"] is False and rev["detail"] == "return terms hidden"
    assert float(mic["total"]) < 300  # under the auto threshold: hidden terms alone caused the escalation
    assert "not disclosed" in mic["offer"]["terms"]


def test_snapshot_and_events_carry_deal_metadata(run):
    snap, items = run
    mon = items["monitors"]
    assert mon["offer"]["seller_id"] and mon["total"] and mon["saving"] is not None
    assert snap["budget"] and snap["ledger_entries"] > 0
    cam = items["webcams"]
    assert cam["seal"]["terms_hash"] and cam["purchase_unit"]["amount"]["value"]
    text = client.get(f"/api/runs/{snap['run_id']}/events?follow=false").text
    events = [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]
    disc = next(e for e in events if e["event"] == "discovered")
    assert disc["candidates"] and {"title", "merchant", "price", "allowlisted"} <= set(disc["candidates"][0])
    neg = next(e for e in events if e["event"] == "negotiated")
    assert any(t.get("from") == "buyer" for t in neg["transcript"])


def test_run_ledger_endpoint_reports_chain_and_filters_by_lineage(run):
    snap, items = run
    base = f"/api/runs/{snap['run_id']}/ledger"
    full = client.get(base).json()
    assert full["chain_ok"] is True and len(full["entries"]) == snap["ledger_entries"]
    one = client.get(base, params={"lineage": items["webcams"]["lineage_id"]}).json()
    assert 0 < len(one["entries"]) < len(full["entries"])


def test_studio_rows_are_scoped_to_the_requested_run(run):
    snap, items = run
    other = client.post("/api/runs").json()  # newer run: the fallback must not leak into run-scoped queries
    rows = client.get("/api/studio/rows", params={"run_id": snap["run_id"]}).json()["rows"]
    cam = next(r for r in rows if r["lineage_id"] == items["webcams"]["lineage_id"])
    assert cam["order_id"] == items["webcams"]["order_id"] and cam["capture_id"] == items["webcams"]["capture_id"]
    assert cam["status"] == "CAPTURED"
    # Lineage and replay order IDs repeat across runs of the same mandate, so make the runs differ in state:
    # settle the monitor in the requested run only, then check each run's rows reflect its own ledger.
    base, mon = f"/api/runs/{snap['run_id']}", items["monitors"]["lineage_id"]
    client.post(f"{base}/decisions/{mon}/approve")
    client.post(f"{base}/orders/{mon}/prepare")
    client.post(f"{base}/orders/{mon}/capture")
    status = lambda rid: {r["lineage_id"]: r.get("status") for r in client.get("/api/studio/rows", params={"run_id": rid}).json()["rows"]}  # noqa: E731
    assert status(snap["run_id"])[mon] == "CAPTURED"
    assert status(other["run_id"]).get(mon) != "CAPTURED"


def test_studio_rows_unknown_run_is_404():
    assert client.get("/api/studio/rows", params={"run_id": "nope"}).status_code == 404


def test_same_mandate_twice_gets_distinct_lineages_and_request_ids():
    """Rehearsing the demo twice live must create two PayPal orders, not replay the first one."""
    from app.core.lineage import request_id

    a, b = client.post("/api/runs").json(), client.post("/api/runs").json()
    assert a["mandate_lineage"] != b["mandate_lineage"]
    cams = [next(i for i in s["items"] if i["need"]["category"] == "webcams") for s in (a, b)]
    assert cams[0]["lineage_id"] != cams[1]["lineage_id"]
    ids = [
        request_id(c["lineage_id"], "s4", "create_order", runs.RUNS[s["run_id"]].items[c["lineage_id"]].decision.decision_digest)
        for c, s in zip(cams, (a, b), strict=True)
    ]
    assert ids[0] != ids[1]
    # Within one run the ID is still stable, so a retry stays idempotent.
    r = client.post(f"/api/runs/{a['run_id']}/orders/{cams[0]['lineage_id']}/retry").json()
    assert r["same_order"] is True
    entry = runs.RUNS[a["run_id"]].rt.ledger.entries(a["mandate_lineage"], "mandate")[0].payload
    assert entry["delegation_id"] == a["run_id"]


def test_studio_rows_carry_timestamps_newest_first(run):
    snap, _ = run
    rows = client.get("/api/studio/rows", params={"run_id": snap["run_id"]}).json()["rows"]
    assert all(r["created_at"] <= r["updated_at"] for r in rows)
    created = [r["created_at"] for r in rows]
    assert created == sorted(created, reverse=True)
    # The last item governed is the first row.
    last = max(snap["items"], key=lambda i: [r["created_at"] for r in rows if r["lineage_id"] == i["lineage_id"]][0])
    assert rows[0]["lineage_id"] == last["lineage_id"]


def test_budget_overspend_prevented_across_concurrent_approvals():
    """BUG-1 regression: two items ($1020 + $590) with a $1500 budget. Both are approved,
    but after the first is prepared/settled, preparing the second raises BudgetExceeded (HTTP 409)."""
    mandate = json.loads(client.post("/api/runs").text)["mandate"]
    mandate["budget"] = "1500"
    mandate["per_txn_cap"] = "1500"
    mandate["auto_threshold"] = "300"
    snap = client.post(
        "/api/runs",
        json={
            "mandate": mandate,
            "needs": [
                {"description": "27in 4K monitor", "category": "monitors", "quantity": 3, "method": "negotiate"},
                {"description": "1080p webcam", "category": "webcams", "quantity": 10, "method": "direct"},
            ],
        },
    ).json()
    base = f"/api/runs/{snap['run_id']}"
    items = {i["need"]["category"]: i for i in snap["items"]}
    mon, cam = items["monitors"], items["webcams"]
    assert float(mon["total"]) == 1020.0
    assert float(cam["total"]) == 590.0
    assert mon["decision"]["route"] == "HUMAN_APPROVAL"
    assert cam["decision"]["route"] == "HUMAN_APPROVAL"

    # Human approves both
    assert client.post(f"{base}/decisions/{mon['lineage_id']}/approve").status_code == 200
    assert client.post(f"{base}/decisions/{cam['lineage_id']}/approve").status_code == 200

    # First order ($1020) prepares cleanly
    r1 = client.post(f"{base}/orders/{mon['lineage_id']}/prepare")
    assert r1.status_code == 200
    assert r1.json()["order_id"]

    # Second order ($590) exceeds $1500 budget ($1020 + $590 = $1610 > $1500) -> 409 BudgetExceeded
    r2 = client.post(f"{base}/orders/{cam['lineage_id']}/prepare")
    assert r2.status_code == 409
    body = r2.json()
    err = body if "code" in body else body.get("detail", {})
    assert err.get("code") == "BUDGET_EXCEEDED"

    # Even after first order captures/settles, second order still cannot overspend
    assert client.post(f"{base}/orders/{mon['lineage_id']}/capture").status_code == 200
    r2_retry = client.post(f"{base}/orders/{cam['lineage_id']}/prepare")
    assert r2_retry.status_code == 409
    err2 = r2_retry.json() if "code" in r2_retry.json() else r2_retry.json().get("detail", {})
    assert err2.get("code") == "BUDGET_EXCEEDED"


def test_abandoned_seal_stops_holding_budget_but_a_capture_never_does():
    """A sealed order PayPal never got approved (popup closed) releases its budget after SEAL_HOLD; a capture is spend for good."""
    from datetime import UTC, datetime

    from app.orchestrator import SEAL_HOLD

    snap = client.post("/api/runs").json()
    run = runs.RUNS[snap["run_id"]]
    mon = next(i for i in snap["items"] if i["need"]["category"] == "monitors")
    base = f"/api/runs/{snap['run_id']}"
    client.post(f"{base}/decisions/{mon['lineage_id']}/approve")
    assert client.post(f"{base}/orders/{mon['lineage_id']}/prepare").status_code == 200
    later = datetime.now(UTC) + SEAL_HOLD * 2

    held = run.rt.committed_spend(run.mandate_lineage)
    assert held >= 1020  # the sealed monitor order counts (the auto-settled webcam captures may add to it)
    assert run.rt.committed_spend(run.mandate_lineage, now=later) == held - 1020  # the abandoned seal has expired

    assert client.post(f"{base}/orders/{mon['lineage_id']}/capture").status_code == 200
    assert run.rt.committed_spend(run.mandate_lineage, now=later) == held  # captured: spend, however long ago


def test_capture_rechecks_budget_when_the_seal_hold_lapsed():
    """The buyer sat on the popup past SEAL_HOLD and another order took the budget: capture must refuse, not overspend."""
    snap = client.post("/api/runs").json()
    run = runs.RUNS[snap["run_id"]]
    mon = next(i for i in snap["items"] if i["need"]["category"] == "monitors")
    base = f"/api/runs/{snap['run_id']}"
    client.post(f"{base}/decisions/{mon['lineage_id']}/approve")
    assert client.post(f"{base}/orders/{mon['lineage_id']}/prepare").status_code == 200
    real = run.rt.committed_spend
    run.rt.committed_spend = lambda *a, **k: real(*a, **k) + 1200  # another order now holds the budget
    res = client.post(f"{base}/orders/{mon['lineage_id']}/capture")
    run.rt.committed_spend = real
    assert res.status_code != 200 and "BUDGET_EXCEEDED" in res.text
    assert not run.rt.ledger.entries(mon["lineage_id"], "capture")
    assert any(e["event"] == "guard" and e.get("code") == "BUDGET_EXCEEDED" for e in run.events)
