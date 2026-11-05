"""scripts/live_dispute_probe.py against a mock PayPal: dry run sends nothing, --send needs the typed ID,
preconditions are checked, and the body is exactly what production sends."""

import importlib.util
import json
from pathlib import Path

import httpx

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


def mock(case=CASE):
    state = {"case": json.loads(json.dumps(case)), "posts": []}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        if req.method == "GET":
            return httpx.Response(200, json=state["case"])
        state["posts"].append((req.url.path, json.loads(req.content)))
        state["case"]["status"] = "WAITING_FOR_BUYER_RESPONSE"
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
