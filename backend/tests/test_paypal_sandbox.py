"""SandboxPayPal against a mock PayPal (no network): request shape, idempotency header, error mapping,
and a live-style order (CREATED until the buyer approves) through the run API."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import runs
from app.integrations.paypal import PayPalAPIError, SandboxPayPal
from app.main import app


class FakePayPal:
    """Just enough of api-m.sandbox.paypal.com: orders start CREATED and capture needs buyer approval."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.orders: dict[str, dict] = {}
        self.approved: set[str] = set()

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        path = req.url.path
        if path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "A21-token", "expires_in": 32400})
        if path == "/v2/checkout/orders":
            body = json.loads(req.content)
            oid = f"5O{len(self.orders):015d}"
            is_vaulted = bool(body.get("payment_source", {}).get("paypal", {}).get("vault_id"))
            status = "APPROVED" if is_vaulted else "CREATED"
            if is_vaulted:
                self.approved.add(oid)
            self.orders[oid] = {"id": oid, "status": status, "purchase_units": body["purchase_units"]}
            return httpx.Response(201, json=self.orders[oid])
        if path.endswith("/capture"):
            oid = path.split("/")[-2]
            if req.headers.get("content-type") != "application/json":
                return httpx.Response(415, json={"name": "UNSUPPORTED_MEDIA_TYPE", "message": "need json"})
            if oid not in self.approved:
                return httpx.Response(
                    422,
                    json={
                        "name": "UNPROCESSABLE_ENTITY",
                        "message": "not approved",
                        "debug_id": "dbg123",
                        "details": [{"issue": "ORDER_NOT_APPROVED"}],
                    },
                )
            pu = self.orders[oid]["purchase_units"][0]
            cap = {"id": "CAP" + oid[-6:], "status": "COMPLETED", "amount": {k: pu["amount"][k] for k in ("currency_code", "value")}}
            return httpx.Response(201, json={"id": oid, "status": "COMPLETED", "purchase_units": [{"payments": {"captures": [cap]}}]})
        return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND", "message": path})


def sandbox(fake: FakePayPal) -> SandboxPayPal:
    gw = SandboxPayPal("cid", "secret", "https://api-m.sandbox.paypal.com")
    gw._http = httpx.Client(base_url="https://api-m.sandbox.paypal.com", transport=httpx.MockTransport(fake))
    return gw


def test_capture_sends_json_content_type_and_request_id():
    fake = FakePayPal()
    gw = sandbox(fake)
    order = gw.create_order({"amount": {"currency_code": "USD", "value": "10.00"}}, "s4-create-abc")
    assert order["status"] == "CREATED"
    fake.approved.add(order["id"])
    cap = gw.capture_order(order["id"], "s4-capture-abc")
    assert cap["purchase_units"][0]["payments"]["captures"][0]["status"] == "COMPLETED"
    req = fake.requests[-1]
    assert req.headers["PayPal-Request-Id"] == "s4-capture-abc" and req.headers["Authorization"] == "Bearer A21-token"
    assert req.content == b""
    assert sum(r.url.path == "/v1/oauth2/token" for r in fake.requests) == 1  # token cached


def test_paypal_errors_keep_name_and_debug_id():
    fake = FakePayPal()
    gw = sandbox(fake)
    order = gw.create_order({"amount": {"currency_code": "USD", "value": "10.00"}}, "r1")
    with pytest.raises(PayPalAPIError) as e:
        gw.capture_order(order["id"], "r2")  # buyer never approved
    assert e.value.status == 422 and e.value.debug_id == "dbg123" and e.value.details[0]["issue"] == "ORDER_NOT_APPROVED"


def test_live_order_waits_for_buyer_then_captures_via_api(monkeypatch):
    """The JS SDK flow: createOrder -> /prepare (CREATED), buyer approves in the popup, onApprove -> /capture."""
    client = TestClient(app)
    snap = client.post("/api/runs").json()
    run = runs.RUNS[snap["run_id"]]
    fake = FakePayPal()
    run.rt.gateway = sandbox(fake)  # this run now talks to a live-shaped PayPal
    mon = next(i for i in snap["items"] if i["need"]["category"] == "monitors")
    base = f"/api/runs/{snap['run_id']}"
    assert client.post(f"{base}/decisions/{mon['lineage_id']}/approve").status_code == 200

    prep = client.post(f"{base}/orders/{mon['lineage_id']}/prepare").json()
    assert prep["status"] == "CREATED"
    sent = json.loads(fake.requests[-1].content)["purchase_units"][0]
    assert sent["custom_id"] == mon["lineage_id"]  # lineage rides on the real order

    early = client.post(f"{base}/orders/{mon['lineage_id']}/capture")  # popup closed / not approved yet
    assert early.status_code == 502 and early.json()["detail"]["details"][0]["issue"] == "ORDER_NOT_APPROVED"
    assert client.get(base).json()["items"][1]["status"] != "settled"

    fake.approved.add(prep["order_id"])
    cap = client.post(f"{base}/orders/{mon['lineage_id']}/capture").json()
    assert cap["status"] == "COMPLETED" and cap["capture_id"].startswith("CAP")
    item = next(i for i in client.get(base).json()["items"] if i["lineage_id"] == mon["lineage_id"])
    assert item["status"] == "settled" and item["order_id"] == prep["order_id"]


def test_health_exposes_client_id_only_when_live(monkeypatch):
    from app.main import settings

    client = TestClient(app)
    assert client.get("/api/health").json()["paypal_client_id"] is None  # replay
    monkeypatch.setattr(settings, "replay_mode", False)
    monkeypatch.setattr(settings, "paypal_client_id", "public-cid")
    monkeypatch.setattr(settings, "paypal_client_secret", "never-sent")
    h = client.get("/api/health").json()
    assert h["paypal_live"] is True and h["paypal_client_id"] == "public-cid"
    assert "never-sent" not in json.dumps(h)


def test_auto_settle_with_saved_wallet_captures_server_side_without_popup(monkeypatch):
    from app.main import settings

    fake = FakePayPal()
    monkeypatch.setattr(settings, "replay_mode", False)
    monkeypatch.setattr(settings, "paypal_client_id", "cid")
    monkeypatch.setattr(settings, "paypal_client_secret", "secret")
    monkeypatch.setattr(settings, "paypal_vault_id", "vault_test_456")
    monkeypatch.setattr("app.orchestrator.make_gateway", lambda s: sandbox(fake))

    client = TestClient(app)
    snap = client.post("/api/runs").json()
    # Webcam is AUTO_SETTLE: with vault_id configured, it is prepared and captured server-side
    webcam = next(i for i in snap["items"] if i["need"]["category"] == "webcams")
    assert webcam["status"] == "settled"
    assert webcam["order_id"].startswith("5O")
    assert webcam["capture_id"].startswith("CAP")

    # Monitor is HUMAN_APPROVAL: remains awaiting approval, not settled
    monitor = next(i for i in snap["items"] if i["need"]["category"] == "monitors")
    assert monitor["status"] == "awaiting_approval"

    # The vault token is a credential: it must never reach the browser or the permanent ledger.
    base = f"/api/runs/{snap['run_id']}"
    bodies = [client.get(base).text, client.get(f"{base}/ledger").text, client.get(f"{base}/events?follow=false").text]
    assert all("vault_test_456" not in b for b in bodies)
    assert webcam["seal"]["payment_source"] == "saved_wallet"

    # Seal-before-money: the terms were sealed before the order (and its capture) existed.
    kinds = [e["kind"] for e in client.get(f"{base}/ledger", params={"lineage": webcam["lineage_id"]}).json()["entries"]]
    assert kinds.index("seal_intent") < kinds.index("seal") < kinds.index("capture")


def test_saved_wallet_is_not_charged_if_the_seal_cannot_be_written(ledger, mandate, monkeypatch):
    from decimal import Decimal

    from app.core.errors import SealWriteFailed
    from app.domain.models import Offer, Proposal
    from app.stages import s03_govern, s04_settle

    fake = FakePayPal()
    gw = sandbox(fake)
    o = Offer(
        seller_id="Contoso Retail", sku="c", turn=1, action="quote", unit_price=Decimal("59"), quantity=1, return_days=30, ship_days=2
    )
    d = s03_govern.evaluate(
        ledger,
        mandate,
        Proposal(
            lineage_id="PG-t.1",
            vendor=o.seller_id,
            category="webcams",
            sku="c",
            unit_price=o.unit_price,
            quantity=1,
            return_days=30,
            baseline_unit_price=o.unit_price,
        ),
        Decimal("0"),
    )
    real = ledger.append
    monkeypatch.setattr(
        ledger,
        "append",
        lambda lid, st, kind, p: (_ for _ in ()).throw(OSError("disk")) if kind == "seal_intent" else real(lid, st, kind, p),
    )
    with pytest.raises(SealWriteFailed):
        s04_settle.prepare_order(ledger, gw, "secret", d, o, title="cam", payment_source={"paypal": {"vault_id": "v"}})
    assert not any(r.url.path == "/v2/checkout/orders" for r in fake.requests)  # PayPal never asked to charge
