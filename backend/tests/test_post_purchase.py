"""One-button stages 5 to 7: verify, reconcile, a refused payout, then a released one. Inputs are scripted."""

import json

from fastapi.testclient import TestClient

from app import runs
from app.main import app

client = TestClient(app)


def _settled():
    snap = client.post("/api/runs").json()
    items = {i["need"]["category"]: i for i in snap["items"]}
    return snap["run_id"], items


def test_sequence_refuses_then_releases():
    run_id, items = _settled()
    cam, mon = items["webcams"], items["monitors"]
    base = f"/api/runs/{run_id}"
    # Awaiting approval, not settled: nothing to verify yet.
    assert client.post(f"{base}/post-purchase/{mon['lineage_id']}").status_code == 409

    res = client.post(f"{base}/post-purchase/{cam['lineage_id']}")
    assert res.status_code == 200
    body = res.json()
    assert body["scripted_inputs"] is True
    assert [(s["stage"], s["outcome"]) for s in body["steps"]] == [
        ("5", "PASS"),
        ("6", "CLEAN"),
        ("6", "FLAGGED"),
        ("7", "refused"),
        ("7", "released"),
    ]
    refusal = next(s for s in body["steps"] if s["outcome"] == "refused")
    assert "GATE_TOKEN_INVALID" in refusal["detail"] or "NOT_AUTHORIZED" in refusal["detail"]
    assert "token" not in {k.lower() for s in body["steps"] for k in s}  # gate tokens never leave the server

    ledger = runs.RUNS[run_id].rt.ledger
    kinds = [e.kind for e in ledger.entries(cam["lineage_id"])]
    assert kinds.count("payout") == 1 and "delivery_proof" in kinds and kinds.count("reconciliation") == 2
    assert ledger.verify()[0] is True
    # The refusal reached the run's event stream, so the timeline shows it.
    assert any(e["event"] == "guard" and e["stage"] == "7" for e in runs.RUNS[run_id].events)


def test_cannot_pay_out_twice_or_for_unknown_lineage():
    run_id, items = _settled()
    base = f"/api/runs/{run_id}"
    lid = items["webcams"]["lineage_id"]
    assert client.post(f"{base}/post-purchase/{lid}").status_code == 200
    again = client.post(f"{base}/post-purchase/{lid}")
    assert again.status_code == 409 and "already" in json.dumps(again.json())
    assert client.post(f"{base}/post-purchase/PG-nope").status_code == 404


def test_each_purchase_is_paid_once_per_run_independently():
    run_id, items = _settled()
    base = f"/api/runs/{run_id}"
    mon = items["monitors"]["lineage_id"]
    client.post(f"{base}/decisions/{mon}/approve")
    client.post(f"{base}/orders/{mon}/prepare")
    client.post(f"{base}/orders/{mon}/capture")
    for lid in (items["webcams"]["lineage_id"], mon):
        out = client.post(f"{base}/post-purchase/{lid}").json()
        assert out["steps"][-1]["outcome"] == "released"  # the second invoice isn't a "duplicate" of the first purchase's


def test_two_purchases_from_one_vendor_get_distinct_invoice_numbers():
    """Webcam and microphone are both Contoso: the second clean invoice must not read as a duplicate of the first."""
    run_id, items = _settled()
    base = f"/api/runs/{run_id}"
    mic = items["microphones"]
    client.post(f"{base}/decisions/{mic['lineage_id']}/approve")
    assert client.post(f"{base}/orders/{mic['lineage_id']}/prepare").status_code == 200
    assert client.post(f"{base}/orders/{mic['lineage_id']}/capture").status_code == 200
    pair = [items["webcams"], mic]
    assert len({runs.RUNS[run_id].item(i["lineage_id"]).offer.seller_id for i in pair}) == 1  # same vendor
    for i in pair:
        body = client.post(f"{base}/post-purchase/{i['lineage_id']}").json()
        assert [s["outcome"] for s in body["steps"]] == ["PASS", "CLEAN", "FLAGGED", "refused", "released"]
