"""scripts/live_dispute_probe.py against a mock PayPal: dry run sends nothing, --send needs the typed ID,
preconditions are checked, and the body is exactly what production sends."""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from app.integrations.paypal import SandboxPayPal

spec = importlib.util.spec_from_file_location("probe", Path(__file__).parents[2] / "scripts" / "live_dispute_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
D = probe.Decimal

CASE = {
    "dispute_id": "PP-R-TST-00000001",
    "reason": "INCORRECT_AMOUNT",
    "status": "WAITING_FOR_SELLER_RESPONSE",
    "dispute_life_cycle_stage": "INQUIRY",
    "dispute_amount": {"currency_code": "USD", "value": "49.99"},
    "allowed_response_options": {"make_offer": {"offer_types": ["REFUND"]}},
    "disputed_transactions": [{"custom": "PG-x.1", "seller_transaction_id": "CAP1"}],
    "links": [{"rel": "make_offer", "method": "POST"}, {"rel": "send_message", "method": "POST"}],
}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(probe.time, "sleep", lambda _: None)


def mock(case=CASE, **flags):
    state = {"case": json.loads(json.dumps(case)), "posts": [], **flags}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        if req.method == "GET":
            if state.get("reads_until_settled") == 0 and not state.get("stuck"):
                state["case"]["status"] = "WAITING_FOR_BUYER_RESPONSE"
            if "reads_until_settled" in state:
                state["reads_until_settled"] -= 1
            return httpx.Response(200, json=state["case"])
        body = json.loads(req.content)
        state["posts"].append((req.url.path, body))
        # Like the live sandbox: briefly UNDER_REVIEW, then waiting on the buyer with the offer on record.
        state["case"]["status"] = "UNDER_REVIEW"
        state["reads_until_settled"] = 1
        state["case"]["offer"] = {
            "buyer_requested_amount": state["case"]["dispute_amount"],
            "seller_offered_amount": body["offer_amount"] if not state.get("tamper") else {"currency_code": "USD", "value": "1.00"},
            "offer_type": body["offer_type"],
            "history": [{"actor": "SELLER", "event_type": "PROPOSED", "offer_type": body["offer_type"]}],
        }
        return httpx.Response(200, json={"links": []})

    gw = SandboxPayPal("c", "s", "https://api-m.sandbox.paypal.com")
    gw._http = httpx.Client(base_url="https://api-m.sandbox.paypal.com", transport=httpx.MockTransport(handler))
    return gw, state


def test_dry_run_sends_nothing():
    gw, st = mock()
    assert probe.probe_offer(gw, CASE["dispute_id"], D("10.00"), send=False) == "DRY_RUN" and st["posts"] == []


def test_send_requires_typing_the_dispute_id():
    gw, st = mock()
    assert probe.probe_offer(gw, CASE["dispute_id"], D("10.00"), send=True, confirm=lambda _: "yes") == "ABORTED"
    assert st["posts"] == []


def test_partial_refund_offer_body_and_pass():
    gw, st = mock()
    assert probe.probe_offer(gw, CASE["dispute_id"], D("10.00"), send=True, confirm=lambda _: CASE["dispute_id"]) == "PASS"
    path, body = st["posts"][0]
    assert path == f"/v1/customer/disputes/{CASE['dispute_id']}/make-offer"
    assert body["offer_type"] == "REFUND" and body["offer_amount"] == {"currency_code": "USD", "value": "10.00"}
    assert "return_shipping_address" not in body


def test_preconditions_block_bad_cases():
    gw, _ = mock()
    assert probe.probe_offer(gw, CASE["dispute_id"], D("60.00"), send=True, confirm=lambda _: CASE["dispute_id"]) == "FAIL"
    gw2, st2 = mock({**CASE, "status": "UNDER_REVIEW", "links": []})
    assert probe.probe_offer(gw2, CASE["dispute_id"], D("10.00"), send=True, confirm=lambda _: CASE["dispute_id"]) == "FAIL"
    assert st2["posts"] == []


def test_pass_needs_paypal_offer_record_to_match_and_not_just_a_status_change():
    gw, _ = mock(tamper=True)  # PayPal records a different amount than we sent
    assert probe.probe_offer(gw, CASE["dispute_id"], D("10.00"), send=True, confirm=lambda _: CASE["dispute_id"]) == "FAIL"
    gw2, _ = mock(stuck=True)  # stays UNDER_REVIEW: not a pass
    assert probe.probe_offer(gw2, CASE["dispute_id"], D("10.00"), send=True, confirm=lambda _: CASE["dispute_id"]) == "FAIL"
