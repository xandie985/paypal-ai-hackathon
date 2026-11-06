"""One test per dispute scenario: each reason's playbook, case states, deadlines, outcomes and the timeline."""

from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app import api, runs
from app.core.ledger import EvidenceLedger
from app.main import app
from app.stages import s08_defend

TODAY = date.today()
ALL_ACTIONS = ["accept_claim", "make_offer", "provide_evidence", "send_message"]
client = TestClient(app)


def purchase(led, lid, *, seller="Contoso Retail", amount="40.00", captured=None, return_days=30, approved=False):
    led.append(lid.split(".")[0], "1-delegate", "mandate", {"digest": "d"})
    led.append(lid, "3-govern", "decision", {"proposal": {"return_days": return_days}, "route": "AUTO_SETTLE"})
    if approved:
        led.append(lid, "3-govern", "approval", {"approver": "ops"})
    order = f"O-{lid[-3:]}"
    led.append(lid, "4-settle", "seal", {"order_id": order, "seller_id": seller, "amount": amount, "terms_hash": "t" * 64})
    value = captured or amount
    led.append(
        lid, "4-settle", "capture", {"order_id": order, "capture_id": f"C-{lid[-3:]}", "amount": {"currency_code": "USD", "value": value}}
    )


def deliver(led, lid, status="DELIVERED", due_by=None):
    led.append(
        lid,
        "5-verify",
        "delivery_proof",
        {
            "order_id": "O",
            "verdict": "PASS" if status == "DELIVERED" else "FAIL",
            "carrier": "UPS",
            "tracking_number": "1Z9",
            "tracking_status": status,
            "due_by": due_by or (TODAY + timedelta(days=3)).isoformat(),
            "delivered_on": TODAY.isoformat(),
        },
    )


def case(reason, lid, *, amount="40.00", note="", stage="INQUIRY", status="WAITING_FOR_SELLER_RESPONSE", actions=None):
    return s08_defend.DisputeCase(
        dispute_id=f"PP-{reason[:6]}",
        reason=reason,
        stage=stage,
        status=status,
        amount=Decimal(amount),
        currency="USD",
        lineage_id=lid,
        capture_id=None,
        item_name="Webcam",
        buyer_note=note,
        due_date=(TODAY + timedelta(days=10)).isoformat(),
        created=f"{TODAY.isoformat()}T08:00:00+00:00",
        actions=ALL_ACTIONS if actions is None else actions,
        allowed_offer_types=["REFUND"] if reason == "MERCHANDISE_OR_SERVICE_NOT_RECEIVED" else ["REFUND", "REFUND_WITH_RETURN"],
    )


def run(c, led, lid):
    a = s08_defend.assess(c, led, lid, TODAY)
    return a, {o["option"]: o for o in a["options"]}


# ---- playbooks, one per reason ------------------------------------------------------------------


def test_inr_with_carrier_proof_is_contested():
    led, lid = EvidenceLedger(), "PG-m.inr"
    purchase(led, lid)
    deliver(led, lid)
    c = case("MERCHANDISE_OR_SERVICE_NOT_RECEIVED", lid, note="never arrived")
    a, o = run(c, led, lid)
    assert a["win_odds"] >= 0.85 and a["recommended"] == "contest"
    assert "refund_with_return" not in o  # goods that never arrived can't be returned
    assert "UPS 1Z9" in s08_defend.draft_reply(c, a, "contest")


def test_inr_in_transit_informs_the_buyer_instead_of_refunding():
    led, lid = EvidenceLedger(), "PG-m.trn"
    purchase(led, lid)
    deliver(led, lid, status="IN_TRANSIT", due_by=(TODAY + timedelta(days=2)).isoformat())
    a, o = run(case("MERCHANDISE_OR_SERVICE_NOT_RECEIVED", lid), led, lid)
    assert o["contest"]["excluded_by"] and o["accept"]["excluded_by"].startswith("The parcel is in transit")
    assert a["recommended"] == "inform" and o["inform"]["via"] == "send_message"


def test_inr_in_transit_but_late_is_refunded():
    led, lid = EvidenceLedger(), "PG-m.lat"
    purchase(led, lid)
    deliver(led, lid, status="IN_TRANSIT", due_by=(TODAY - timedelta(days=1)).isoformat())
    a, o = run(case("MERCHANDISE_OR_SERVICE_NOT_RECEIVED", lid), led, lid)
    assert "inform" not in o and a["recommended"] == "accept"


def test_inr_without_tracking_refunds_and_never_offers_a_return():
    led, lid = EvidenceLedger(), "PG-m.nop"
    purchase(led, lid)
    a, o = run(case("MERCHANDISE_OR_SERVICE_NOT_RECEIVED", lid), led, lid)
    assert "record tracking" in o["contest"]["excluded_by"] and a["recommended"] == "accept"
    assert set(o) == {"contest", "accept"}


def test_duplicate_charge_found_in_ledger_is_refunded():
    led = EvidenceLedger()
    purchase(led, "PG-m.aaa")
    purchase(led, "PG-m.bbb")  # same vendor, same amount, moments apart
    a, o = run(case("DUPLICATE_TRANSACTION", "PG-m.bbb"), led, "PG-m.bbb")
    assert o["contest"]["excluded_by"].startswith("A second capture") and a["recommended"] == "accept"
    assert any("Duplicate capture" in f for f in a["flags"])


def test_duplicate_claim_with_one_capture_is_contested():
    led, lid = EvidenceLedger(), "PG-m.one"
    purchase(led, lid)
    a, _ = run(case("DUPLICATE_TRANSACTION", lid), led, lid)
    assert a["win_odds"] >= 0.9 and a["recommended"] == "contest"


def test_overcharge_gets_a_partial_refund_of_the_difference():
    led, lid = EvidenceLedger(), "PG-m.ovr"
    purchase(led, lid, amount="40.00", captured="52.00")
    a, o = run(case("INCORRECT_AMOUNT", lid, amount="52.00"), led, lid)
    assert o["contest"]["excluded_by"] and o["partial_refund"]["amount"] == "12.00"
    assert a["recommended"] == "partial_refund" and o["partial_refund"]["ev"] == Decimal("40.00")
    assert "12.00 difference" in s08_defend.draft_reply(case("INCORRECT_AMOUNT", lid, amount="52.00"), a, "partial_refund")


def test_correct_amount_is_contested_from_the_penny_exact_seal():
    led, lid = EvidenceLedger(), "PG-m.ok"
    purchase(led, lid)
    a, _ = run(case("INCORRECT_AMOUNT", lid), led, lid)
    assert a["win_odds"] >= 0.85 and a["recommended"] == "contest"


def test_promised_refund_is_honoured():
    led, lid = EvidenceLedger(), "PG-m.crd"
    purchase(led, lid)
    led.append(lid, "8-defend", "dispute_response", {"dispute_id": "PP-OLD", "option": "refund_with_return", "via": "make_offer"})
    a, o = run(case("CREDIT_NOT_PROCESSED", lid), led, lid)
    assert o["contest"]["excluded_by"].startswith("We committed to a refund") and a["recommended"] != "contest"
    assert any("disputed before" in f for f in a["flags"])


def test_unauthorised_is_flagged_and_needs_delivery_plus_approval():
    led, lid = EvidenceLedger(), "PG-m.una"
    purchase(led, lid, approved=True)
    a, _ = run(case("UNAUTHORISED", lid), led, lid)
    assert a["win_odds"] <= 0.15 and any("compromised" in f for f in a["flags"])
    deliver(led, lid)
    a2, _ = run(case("UNAUTHORISED", lid), led, lid)
    assert a2["win_odds"] > 0.5


def test_single_capture_proves_recurring_and_other_means_claims():
    for reason in ("CANCELED_RECURRING_BILLING", "PAYMENT_BY_OTHER_MEANS"):
        led, lid = EvidenceLedger(), "PG-m.rec"
        purchase(led, lid)
        a, _ = run(case(reason, lid), led, lid)
        assert a["win_odds"] >= 0.8 and a["recommended"] == "contest", reason


def test_unknown_reason_gets_no_automatic_recommendation():
    led, lid = EvidenceLedger(), "PG-m.unk"
    purchase(led, lid)
    a, _ = run(case("PROBLEM_WITH_REMITTANCE", lid), led, lid)
    assert a["recommended"] is None and any("review manually" in f for f in a["flags"])


# ---- case state, cost and sanity checks ----------------------------------------------------------


def test_only_cases_waiting_on_us_get_a_recommendation():
    led, lid = EvidenceLedger(), "PG-m.st"
    purchase(led, lid)
    for status in ("WAITING_FOR_BUYER_RESPONSE", "UNDER_REVIEW"):
        a, _ = run(case("DUPLICATE_TRANSACTION", lid, status=status, actions=["send_message"]), led, lid)
        assert a["recommended"] is None and a["state_note"]


def test_chargeback_costs_more_to_fight():
    led, lid = EvidenceLedger(), "PG-m.cb"
    purchase(led, lid)
    _, inq = run(case("DUPLICATE_TRANSACTION", lid), led, lid)
    _, cb = run(case("DUPLICATE_TRANSACTION", lid, stage="CHARGEBACK"), led, lid)
    assert inq["contest"]["ev"] - cb["contest"]["ev"] == 5


def test_more_disputed_than_captured_is_flagged():
    led, lid = EvidenceLedger(), "PG-m.big"
    purchase(led, lid, amount="40.00")
    a, _ = run(case("DUPLICATE_TRANSACTION", lid, amount="90.00"), led, lid)
    assert any("more than the 40.00 captured" in f for f in a["flags"])


# ---- through the API (replay) --------------------------------------------------------------------


def settled_webcam():
    snap = client.post("/api/runs").json()
    cam = next(i for i in snap["items"] if i["need"]["category"] == "webcams")
    return snap["run_id"], cam


def simulate(run_id, lid, reason, note=""):
    r = client.post(f"/api/runs/{run_id}/disputes/simulate", json={"lineage_id": lid, "reason": reason, "note": note})
    assert r.status_code == 200, r.text
    return r.json()["dispute_id"]


def test_record_delivery_then_contest_an_inr_end_to_end():
    run_id, cam = settled_webcam()
    did = simulate(run_id, cam["lineage_id"], "MERCHANDISE_OR_SERVICE_NOT_RECEIVED", "it never arrived")
    assert client.get(f"/api/disputes/{did}").json()["assessment"]["recommended"] == "accept"
    r = client.post(
        "/api/deliveries",
        json={
            "lineage_id": cam["lineage_id"],
            "carrier": "FedEx",
            "tracking_number": "7489",
            "tracking_status": "DELIVERED",
            "delivered_on": TODAY.isoformat(),
            "due_by": (TODAY + timedelta(days=1)).isoformat(),
        },
    )
    assert r.status_code == 200 and r.json() == {"verdict": "PASS", "problems": []}  # no gate token on the wire
    after = client.get(f"/api/disputes/{did}").json()["assessment"]
    assert after["recommended"] == "contest" and after["facts"]["tracking"]["number"] == "7489"
    assert client.post(f"/api/disputes/{did}/respond", json={"option": "contest", "note": "Delivered by FedEx 7489."}).status_code == 200
    ev = api.disputes_gateway().evidence[did]["evidence"]["evidences"][0]
    assert ev["evidence_type"] == "PROOF_OF_FULFILLMENT" and ev["evidence_info"]["tracking_info"][0]["tracking_number"] == "7489"


def test_delivery_for_unknown_lineage_is_404():
    body = {"lineage_id": "PG-nope.1", "carrier": "x", "tracking_number": "1", "tracking_status": "DELIVERED", "due_by": TODAY.isoformat()}
    assert client.post("/api/deliveries", json=body).status_code == 404


def test_timeline_is_dated_and_ordered_and_outcome_is_learned_once():
    run_id, cam = settled_webcam()
    did = simulate(run_id, cam["lineage_id"], "DUPLICATE_TRANSACTION", "charged twice")
    assert client.post(f"/api/disputes/{did}/respond", json={"option": "contest", "note": "One order, one payment."}).status_code == 200
    d = client.get(f"/api/disputes/{did}").json()
    whos = [e["who"] for e in d["timeline"]]
    assert whos[0] == "ledger" and "buyer" in whos and "us" in whos and whos[-1] == "deadline"
    stamps = [e["at"] for e in d["timeline"] if e["who"] != "deadline"]
    assert all(stamps) and stamps == sorted(stamps, key=s08_defend._as_utc)

    res = client.post(f"/api/disputes/{did}/simulate-resolve", json={"outcome_code": "RESOLVED_SELLER_FAVOUR"}).json()
    assert "(won)" in res["assessment"]["state_note"].lower() and res["assessment"]["recommended"] is None
    client.get(f"/api/disputes/{did}")  # looking again must not record the outcome twice
    outcomes = runs.RUNS[run_id].rt.ledger.entries(cam["lineage_id"], "dispute_outcome")
    assert [e.payload["outcome"] for e in outcomes] == ["WON"] and outcomes[0].payload["seller_id"] == "Contoso Retail"
    listed = {x["case"]["dispute_id"]: x for x in client.get("/api/disputes").json()}
    assert listed[did]["case"]["created"] and listed[did]["state_note"]
