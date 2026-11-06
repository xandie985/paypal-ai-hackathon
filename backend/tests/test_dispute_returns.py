"""Return lifecycle, as run live on PP-R-PSL-10196709: refund-with-return offer -> buyer ships ->
we inspect what arrived -> acknowledge -> PayPal refunds -> outcome recorded as SETTLED, not LOST."""

from fastapi.testclient import TestClient

from app import api, runs
from app.main import app

client = TestClient(app)


def returned_case(note="it stopped working, i will return it"):
    """A not-as-described case where we offered a refund on return and the buyer uploaded tracking."""
    snap = client.post("/api/runs").json()
    cam = next(i for i in snap["items"] if i["need"]["category"] == "webcams")
    r = client.post(
        f"/api/runs/{snap['run_id']}/disputes/simulate", json={"lineage_id": cam["lineage_id"], "amount": "14.00", "note": note}
    )
    did = r.json()["dispute_id"]
    sent = client.post(f"/api/disputes/{did}/respond", json={"option": "refund_with_return", "note": "Send it back for a refund."})
    assert sent.status_code == 200, sent.text
    shipped = client.post(f"/api/disputes/{did}/simulate-return", json={"carrier": "UPS", "tracking_number": "1Z9999999999999999"})
    assert shipped.status_code == 200, shipped.text
    return snap["run_id"], cam["lineage_id"], did


def opts(did):
    a = client.get(f"/api/disputes/{did}").json()["assessment"]
    return a, {o["option"]: o for o in a["options"]}


def test_buyer_tracking_alone_never_triggers_a_refund():
    _, _, did = returned_case()
    a, o = opts(did)
    assert a["facts"]["return_tracking"]["number"] == "1Z9999999999999999"
    assert o["acknowledge_return"]["excluded_by"].startswith("Record what arrived first")
    assert a["recommended"] is None and "Wait for the parcel" in a["state_note"]
    r = client.post(f"/api/disputes/{did}/respond", json={"option": "acknowledge_return", "note": "x"})
    assert r.status_code == 409 and ("acknowledge_return_item", did) not in api.disputes_gateway().calls


def test_good_return_is_acknowledged_refunded_and_labelled_settled():
    run_id, lid, did = returned_case()
    r = client.post(f"/api/disputes/{did}/return-received", json={"condition": "ITEM_RECEIVED", "note": "unit intact"})
    assert r.status_code == 200
    a, o = opts(did)
    assert a["recommended"] == "acknowledge_return" and not o["acknowledge_return"]["excluded_by"]
    assert client.post(f"/api/disputes/{did}/return-received", json={"condition": "ITEM_RECEIVED"}).status_code == 409  # once
    sent = client.post(f"/api/disputes/{did}/respond", json={"option": "acknowledge_return", "note": "Received, refunding."})
    assert sent.status_code == 200 and sent.json()["case"]["status"] == "RESOLVED"
    assert api.disputes_gateway().disputes[did]["status"] == "RESOLVED"
    d = client.get(f"/api/disputes/{did}").json()
    assert "(SETTLED)" in d["assessment"]["state_note"]
    assert any("Return inspected: item received" in e["what"] for e in d["timeline"])
    assert d["timeline"][-1]["who"] == "paypal" and "SETTLED" in d["timeline"][-1]["what"]
    led = runs.RUNS[run_id].rt.ledger
    assert [e.payload["outcome"] for e in led.entries(lid, "dispute_outcome")] == ["SETTLED"]
    kinds = [e.kind for e in led.entries(lid) if e.kind in ("dispute_response", "return_received", "dispute_outcome")]
    assert kinds == ["dispute_response", "return_received", "dispute_response", "dispute_outcome"]


def test_damaged_return_is_reported_not_refunded():
    _, _, did = returned_case()
    client.post(f"/api/disputes/{did}/return-received", json={"condition": "DAMAGED", "note": "cracked housing, not in original state"})
    a, o = opts(did)
    assert o["acknowledge_return"]["condition"] == "DAMAGED" and "PayPal reviews" in o["acknowledge_return"]["basis"]
    draft = client.get(f"/api/disputes/{did}").json()["drafts"]["acknowledge_return"]
    assert "arrived damaged" in draft and "asking PayPal to review" in draft
    client.post(f"/api/disputes/{did}/respond", json={"option": "acknowledge_return", "note": draft})
    body_sent = api.disputes_gateway().disputes[did]
    assert body_sent["status"] == "UNDER_REVIEW"  # not refunded


def test_return_inspection_rules():
    _, _, did = returned_case()
    assert client.post(f"/api/disputes/{did}/return-received", json={"condition": "LOOKS_FINE"}).status_code == 422
    snap = client.post("/api/runs").json()
    cam = next(i for i in snap["items"] if i["need"]["category"] == "webcams")
    fresh = client.post(f"/api/runs/{snap['run_id']}/disputes/simulate", json={"lineage_id": cam["lineage_id"]}).json()["dispute_id"]
    assert client.post(f"/api/disputes/{fresh}/return-received", json={}).status_code == 409  # no return expected
    assert client.post(f"/api/disputes/{fresh}/simulate-return", json={}).status_code == 409  # no return offer made


def test_settled_outcome_does_not_tighten_the_mandate_but_counts_against_supplier():
    from app.orchestrator import DEMO_MANDATE
    from app.stages import s10_learn

    run_id, lid, did = returned_case()
    client.post(f"/api/disputes/{did}/return-received", json={"condition": "ITEM_RECEIVED"})
    client.post(f"/api/disputes/{did}/respond", json={"option": "acknowledge_return", "note": "ok"})
    client.get(f"/api/disputes/{did}")
    run = runs.RUNS[run_id]
    cal = s10_learn.calibrate(run.rt.ledger, DEMO_MANDATE, run.mandate_lineage)
    assert not any("auto_threshold" in c and "lost dispute" in c for c in cal["changes"])
    assert cal["trust"]["Contoso Retail"] < 2 / 3  # below the Beta(2,1) prior: the settlement is a quality signal
