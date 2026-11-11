"""Stage 7 webhooks: verified against the raw bytes, de-duplicated durably, stored and replayable."""

import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app import api
from app.config import settings
from app.core.ledger import EvidenceLedger
from app.integrations.paypal import ReplayPayPal, SandboxPayPal
from app.main import app
from app.stages import s07_payout

client = TestClient(app)
SIGNED = {"paypal-transmission-sig": "sig"}


def event_id() -> str:
    return f"WH-{uuid.uuid4().hex[:10]}"


def test_a_signed_delivery_is_stored_and_a_retry_is_acknowledged_as_a_duplicate():
    eid = event_id()
    raw = json.dumps({"id": eid, "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {"custom_id": "PG-abc"}}).encode()
    first = client.post("/api/webhooks/paypal", content=raw, headers=SIGNED)
    again = client.post("/api/webhooks/paypal", content=raw, headers=SIGNED)
    assert first.status_code == again.status_code == 200  # a non-2xx would make PayPal retry
    assert first.json() == {"event_id": eid, "duplicate": False, "lineage_id": "PG-abc"}
    assert again.json() == {"event_id": eid, "duplicate": True}


def test_the_gateway_gets_the_exact_bytes_that_were_delivered(monkeypatch):
    seen = {}

    def verify(headers, body, raw=None):
        seen.update(headers=headers, body=body, raw=raw)
        return True

    monkeypatch.setattr(api.runtime().gateway, "verify_webhook", verify)
    # Key order, spacing and a trailing newline: all lost by parse-and-redump, all part of what PayPal signed.
    raw = b'{"resource" :{"custom_id":"PG-x"},\n  "id":"' + event_id().encode() + b'", "event_type":"X"}\n'
    assert client.post("/api/webhooks/paypal", content=raw, headers={"PayPal-Transmission-Sig": "s"}).status_code == 200
    assert seen["raw"] == raw
    assert seen["headers"]["paypal-transmission-sig"] == "s"  # header names are lower-cased for lookup


def test_an_unverifiable_delivery_is_401_and_stores_nothing():
    eid = event_id()
    r = client.post("/api/webhooks/paypal", json={"id": eid, "event_type": "X"})  # no signature header
    assert r.status_code == 401 and r.json()["detail"]["code"] == "WEBHOOK_UNVERIFIED"
    assert eid not in [e["event_id"] for e in client.get("/api/webhooks").json()["events"]]


@pytest.mark.parametrize("raw", [b"not json", b'["a list"]', b'{"event_type": "no id"}'])
def test_malformed_deliveries_are_400(raw):
    assert client.post("/api/webhooks/paypal", content=raw, headers=SIGNED).status_code == 400


def test_dedupe_survives_a_restart_because_the_ledger_is_the_store():
    ledger = EvidenceLedger(":memory:")
    evt = {"id": "WH-7", "event_type": "INVOICING.INVOICE.PAID", "resource": {"custom_id": "PG-1"}}
    assert s07_payout.WebhookInbox(ledger, ReplayPayPal()).receive(SIGNED, evt)["duplicate"] is False
    restarted = s07_payout.WebhookInbox(ledger, ReplayPayPal())  # a new process: no in-memory state
    assert restarted.receive(SIGNED, evt)["duplicate"] is True
    assert restarted.replay("WH-7") == evt
    assert len(ledger.entries(kind="webhook")) == 1


def test_listing_is_newest_first_and_replay_returns_the_stored_event():
    a, b = event_id(), event_id()
    for eid in (a, b):
        client.post("/api/webhooks/paypal", json={"id": eid, "event_type": "X", "summary": f"s-{eid}"}, headers=SIGNED)
    ids = [e["event_id"] for e in client.get("/api/webhooks").json()["events"]]
    assert ids.index(b) < ids.index(a)
    assert client.post(f"/api/webhooks/{a}/replay").json()["summary"] == f"s-{a}"
    assert client.post("/api/webhooks/WH-nope/replay").status_code == 404


def test_simulate_goes_through_the_real_inbox_and_dedupes_by_id():
    eid = event_id()
    body = {"event_type": "PAYMENT.CAPTURE.COMPLETED", "lineage_id": "PG-sim", "event_id": eid}
    first = client.post("/api/webhooks/simulate", json=body).json()
    again = client.post("/api/webhooks/simulate", json=body).json()
    assert (first["duplicate"], again["duplicate"]) == (False, True)
    assert first["lineage_id"] == "PG-sim" and first["event"]["event_type"] == "PAYMENT.CAPTURE.COMPLETED"


def test_simulate_is_refused_in_live_mode(monkeypatch):
    monkeypatch.setattr(settings, "replay_mode", False)
    assert client.post("/api/webhooks/simulate", json={}).status_code == 409


# --- the live client: the received bytes are spliced into the verify request untouched ------------------


def sandbox(status: str):
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["content"] = request.content
        sent["path"] = request.url.path
        return httpx.Response(200, json={"verification_status": status})

    gw = SandboxPayPal("id", "secret", "https://api-m.sandbox.paypal.com", webhook_id="WEBHOOK-ID")
    gw._http = httpx.Client(base_url="https://api-m.sandbox.paypal.com", transport=httpx.MockTransport(handler))
    gw._bearer = lambda: "token"
    return gw, sent


HEADERS = {
    "PAYPAL-AUTH-ALGO": "SHA256withRSA",
    "PAYPAL-CERT-URL": "https://api.sandbox.paypal.com/cert.pem",
    "PAYPAL-TRANSMISSION-ID": "tid",
    "PAYPAL-TRANSMISSION-SIG": "sig",
    "PAYPAL-TRANSMISSION-TIME": "2026-11-06T10:00:00Z",
}


def test_live_verification_embeds_the_raw_event_verbatim():
    gw, sent = sandbox("SUCCESS")
    raw = b'{"resource": {"amount": {"value": "10.10"}},  "id": "WH-1",\n "n": 1e2, "u": "\\u00e9"}\n'
    assert gw.verify_webhook(HEADERS, json.loads(raw), raw) is True
    assert sent["path"] == "/v1/notifications/verify-webhook-signature"
    assert b'"webhook_event": ' + raw.strip() in sent["content"]  # byte for byte, including 1e2 and the escape
    envelope = json.loads(sent["content"])
    assert envelope["webhook_id"] == "WEBHOOK-ID" and envelope["transmission_id"] == "tid"
    assert envelope["webhook_event"]["id"] == "WH-1"


def test_live_verification_failure_is_false():
    gw, _ = sandbox("FAILURE")
    assert gw.verify_webhook(HEADERS, {"id": "WH-1"}, b'{"id": "WH-1"}') is False


def test_parsed_body_path_is_unchanged_without_raw_bytes():
    gw, sent = sandbox("SUCCESS")
    assert gw.verify_webhook(HEADERS, {"id": "WH-1"}) is True
    assert json.loads(sent["content"])["webhook_event"] == {"id": "WH-1"}
