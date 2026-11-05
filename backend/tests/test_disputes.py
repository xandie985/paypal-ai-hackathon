"""Stage 8 dispute desk: parse real PayPal disputes, assess rationally, respond only on a human's go-ahead."""

import json
from datetime import date, timedelta
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app import api, runs
from app.core import ledger as ledger_mod
from app.core.ledger import open_ledger
from app.integrations.paypal import SandboxPayPal
from app.main import app
from app.stages import s08_defend

client = TestClient(app)
RAW = json.loads((Path(__file__).parent / "fixtures" / "paypal_dispute_inquiry.json").read_text())


def settled(category: str) -> tuple[str, dict]:
    """Start a replay run and get the item for `category` to settled (approving it if needed)."""
    snap = client.post("/api/runs").json()
    item = next(i for i in snap["items"] if i["need"]["category"] == category)
    base = f"/api/runs/{snap['run_id']}"
    if item["status"] == "awaiting_approval":
        client.post(f"{base}/decisions/{item['lineage_id']}/approve")
    if item["status"] != "settled":
        client.post(f"{base}/orders/{item['lineage_id']}/prepare")
        client.post(f"{base}/orders/{item['lineage_id']}/capture")
    return snap["run_id"], item


def open_case(run_id: str, lineage: str, **kw) -> str:
    r = client.post(f"/api/runs/{run_id}/disputes/simulate", json={"lineage_id": lineage, **kw})
    assert r.status_code == 200, r.text
    return r.json()["dispute_id"]


def test_parses_the_real_sandbox_dispute():
    case = s08_defend.parse_paypal_dispute(RAW)
    assert case.lineage_id == "PG-986dd7cd20d6febc.9d975a51f6" and case.capture_id == "6ET18262NT9758442"
    assert str(case.amount) == "30.00" and case.stage == "INQUIRY" and case.actions == ["send_message"]
    assert s08_defend.classify_note(case.buyer_note) == "defect"


def test_real_case_without_its_ledger_is_never_contested_blind():
    """The live case's run ledger was in memory and is gone: no evidence, so no contest."""
    case = s08_defend.parse_paypal_dispute(RAW)
    a = s08_defend.assess(case, None, case.lineage_id, date(2026, 11, 5))
    contest = a["options"][0]
    assert a["facts"]["lineage_found"] is False and contest["excluded_by"]
    # PayPal allows only send_message here, so the return is proposed in a message rather than as a formal offer.
    assert all(o["via"] == "send_message" and o["available"] for o in a["options"])
    assert a["recommended"] == "refund_with_return"


def test_defect_claim_on_hidden_terms_item_recommends_refund_with_return():
    """The live scenario, end to end in replay: $30 'stopped working' claim on the microphone (terms hidden)."""
    run_id, mic = settled("microphones")
    did = open_case(run_id, mic["lineage_id"], amount="30.00")
    d = client.get(f"/api/disputes/{did}").json()
    a = d["assessment"]
    assert a["facts"]["lineage_found"] and a["facts"]["sealed_return_days"] is None and a["facts"]["claim"] == "defect"
    assert a["facts"]["human_approved"] is True and a["facts"]["chain_ok"] is True
    assert a["win_odds"] <= 0.35  # a seal can't prove the unit still works
    ev = {o["option"]: float(o["ev"]) for o in a["options"]}
    assert ev["contest"] < 0 < ev["refund_with_return"]
    assert a["recommended"] == "refund_with_return"
    assert "refund 30.00 USD" in d["drafts"]["refund_with_return"]


def test_respond_needs_an_allowed_action_and_records_it_once():
    run_id, mic = settled("microphones")
    did = open_case(run_id, mic["lineage_id"], amount="30.00")
    gw = api.disputes_gateway()
    r = client.post(f"/api/disputes/{did}/respond", json={"option": "contest", "note": "Sealed record attached."})
    assert r.status_code == 200 and r.json()["case"]["status"] == "WAITING_FOR_SELLER_RESPONSE"
    again = client.post(f"/api/disputes/{did}/respond", json={"option": "contest", "note": "again"})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "DISPUTE_ALREADY_ANSWERED"
    sent = [c for c in gw.calls if c[1] == did]
    assert sent == [("provide_evidence", did)]  # the duplicate never reached PayPal
    offer = client.post(f"/api/disputes/{did}/respond", json={"option": "refund_with_return", "note": "We'll refund on return."})
    assert offer.status_code == 200 and offer.json()["case"]["status"] == "WAITING_FOR_BUYER_RESPONSE"
    # After the offer PayPal only lists send_message: accepting goes out as a message, never as accept_claim.
    detail = client.get(f"/api/disputes/{did}").json()["assessment"]
    assert {o["option"]: o["via"] for o in detail["options"]} == {
        "contest": "send_message",
        "refund_with_return": "send_message",
        "accept": "send_message",
    }
    repeat = client.post(f"/api/disputes/{did}/respond", json={"option": "contest", "note": "x"})
    assert repeat.status_code == 409 and repeat.json()["detail"]["code"] == "DISPUTE_ALREADY_ANSWERED"
    assert client.post(f"/api/disputes/{did}/respond", json={"option": "accept", "note": "x"}).status_code == 200
    assert ("accept_claim", did) not in gw.calls and ("send_message", did) in gw.calls
    led = runs.RUNS[run_id].rt.ledger
    resp = [e.payload for e in led.entries(mic["lineage_id"], "dispute_response")]
    assert [p["option"] for p in resp] == ["contest", "refund_with_return", "accept"]
    assert resp[1]["followed_recommendation"] is True and "Sealed record" not in json.dumps(resp)  # note stored as a hash


def test_inside_the_sealed_return_window_we_do_not_contest():
    run_id, cam = settled("webcams")  # replay webcam: 30-day returns, bought today
    did = open_case(run_id, cam["lineage_id"], note="the picture is not what was described")
    a = client.get(f"/api/disputes/{did}").json()["assessment"]
    assert a["facts"]["within_return_window"] is True and a["facts"]["claim"] == "other"
    contest = a["options"][0]
    assert "return window" in contest["excluded_by"] and a["recommended"] != "contest"
    r = client.post(f"/api/disputes/{did}/respond", json={"option": "contest", "note": "no"})
    assert r.status_code == 409


def test_brief_pdf_and_listing():
    run_id, mic = settled("microphones")
    did = open_case(run_id, mic["lineage_id"])
    pdf = client.get(f"/api/disputes/{did}/brief.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    listed = {d["case"]["dispute_id"]: d for d in client.get("/api/disputes").json()}
    assert listed[did]["lineage_found"] is True and listed[did]["recommended"]


def test_simulate_is_replay_only_and_needs_a_settled_item():
    snap = client.post("/api/runs").json()
    mon = next(i for i in snap["items"] if i["need"]["category"] == "monitors")
    r = client.post(f"/api/runs/{snap['run_id']}/disputes/simulate", json={"lineage_id": mon["lineage_id"]})
    assert r.status_code == 409


def test_draft_endpoint_falls_back_to_template_without_a_key():
    run_id, mic = settled("microphones")
    did = open_case(run_id, mic["lineage_id"])
    r = client.post(f"/api/disputes/{did}/draft", json={"option": "accept"}).json()
    assert r["source"] == "template" and "refunding" in r["text"]


def test_live_evidence_survives_a_restart(tmp_path):
    """Live runs write to one ledger file; after a restart the seal is still found by lineage or capture ID."""
    path = str(tmp_path / "ledger.db")
    led = open_ledger(path)
    assert open_ledger(path) is led  # one object per file, so appends can't race
    led.append("PG-x.1", "4-settle", "seal", {"order_id": "O1", "terms_hash": "h" * 64})
    led.append("PG-x.1", "4-settle", "capture", {"order_id": "O1", "capture_id": "6ET18262NT9758442", "amount": {}})
    ledger_mod._SHARED.clear()  # simulate a new process
    fresh = open_ledger(path)
    case = s08_defend.parse_paypal_dispute({**RAW, "disputed_transactions": [{**RAW["disputed_transactions"][0], "custom": None}]})
    found, lineage = s08_defend.locate(case, [fresh])
    assert found is fresh and lineage == "PG-x.1"  # matched by capture ID when custom is missing


def test_sandbox_dispute_calls_use_paypal_paths():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.method, req.url.path))
        if req.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        if req.method == "GET" and req.url.path == "/v1/customer/disputes":
            return httpx.Response(200, json={"items": [{"dispute_id": RAW["dispute_id"]}]})
        if req.method == "GET":
            return httpx.Response(200, json=RAW)
        return httpx.Response(200, json={"links": []})

    gw = SandboxPayPal("c", "s", "https://api-m.sandbox.paypal.com")
    gw._http = httpx.Client(base_url="https://api-m.sandbox.paypal.com", transport=httpx.MockTransport(handler))
    assert gw.list_disputes()[0]["dispute_id"] == RAW["dispute_id"]
    assert gw.get_dispute(RAW["dispute_id"])["reason"] == RAW["reason"]
    gw.dispute_action(RAW["dispute_id"], "send_message", {"message": "hi"})
    gw.dispute_action(RAW["dispute_id"], "make_offer", {"note": "n"})
    paths = [p for m, p in seen if m == "POST" and "disputes" in p]
    assert paths == [f"/v1/customer/disputes/{RAW['dispute_id']}/send-message", f"/v1/customer/disputes/{RAW['dispute_id']}/make-offer"]


def test_closed_window_excludes_everything():
    case = s08_defend.parse_paypal_dispute({**RAW, "seller_response_due_date": (date.today() - timedelta(days=1)).isoformat()})
    a = s08_defend.assess(case, None, None, date.today())
    assert a["recommended"] is None and all(o["excluded_by"] for o in a["options"])


def test_money_is_a_decimal_string_on_the_wire():
    run_id, mic = settled("microphones")
    did = open_case(run_id, mic["lineage_id"], amount="30.00")
    d = client.get(f"/api/disputes/{did}").json()
    assert d["case"]["amount"] == "30.00" and isinstance(d["assessment"]["options"][0]["ev"], str)


def test_refund_on_return_needs_a_configured_return_address(monkeypatch):
    """Live: PayPal rejects REFUND_WITH_RETURN without an address, so we refuse before calling, and never invent one."""
    from app.main import settings

    run_id, mic = settled("microphones")
    did = open_case(run_id, mic["lineage_id"], amount="30.00")
    gw = api.disputes_gateway()
    monkeypatch.setattr(settings, "replay_mode", False)  # live rules for the address; the replay gateway stays
    monkeypatch.setattr(settings, "return_address_line_1", "")
    a = client.get(f"/api/disputes/{did}").json()["assessment"]
    assert "returns address" in a["options"][1]["excluded_by"] and a["recommended"] != "refund_with_return"
    r = client.post(f"/api/disputes/{did}/respond", json={"option": "refund_with_return", "note": "x"})
    assert r.status_code == 409 and ("make_offer", did) not in gw.calls
    monkeypatch.setattr(settings, "return_address_line_1", "9 Dock St")
    monkeypatch.setattr(settings, "return_address_city", "Austin")
    monkeypatch.setattr(settings, "return_address_postal_code", "78701")
    assert client.post(f"/api/disputes/{did}/respond", json={"option": "refund_with_return", "note": "ok"}).status_code == 200
    sent = gw.get_dispute(did)["offer"]["return_shipping_address"]
    assert sent["address_line_1"] == "9 Dock St" and sent["postal_code"] == "78701"


def test_replay_double_rejects_an_offer_without_address_like_paypal():
    import pytest

    from app.integrations.paypal import PayPalAPIError, ReplayPayPal

    gw = ReplayPayPal()
    d = gw.open_dispute(lineage_id="L", capture_id="C", amount="1.00", reason="X", note="", item_name="i")
    with pytest.raises(PayPalAPIError) as e:
        gw.dispute_action(d["dispute_id"], "make_offer", {"offer_type": "REFUND_WITH_RETURN", "note": "n"})
    assert e.value.details[0]["issue"] == "MISSING_RETURN_SHIPPING_ADDRESS" and gw.calls == []
