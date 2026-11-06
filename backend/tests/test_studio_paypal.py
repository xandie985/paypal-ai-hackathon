"""GET /api/studio/paypal: replay fixture shape, and the live path against a mock PayPal (no network)."""

from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app import studio_paypal
from app.integrations.paypal import PayPalAPIError, SandboxPayPal
from app.main import app

TABLES = ["customers", "invoices", "invoiceItems", "invoicePayments", "products", "plans", "transactions", "payouts", "balances"]


def test_replay_fixture_has_every_related_table():
    body = TestClient(app).get("/api/studio/paypal").json()
    assert body["source"] == "replay" and body["asOf"] == "2026-11-05T12:00:00Z"
    assert all(body[t] for t in TABLES)
    # The relationships the report depends on resolve inside the fixture.
    customers = {c["id"] for c in body["customers"]}
    invoices = {i["id"] for i in body["invoices"]}
    products = {p["id"] for p in body["products"]}
    assert {i["customerId"] for i in body["invoices"]} <= customers
    assert {i["invoiceId"] for i in body["invoiceItems"]} <= invoices
    assert {p["invoiceId"] for p in body["invoicePayments"]} <= invoices
    assert {p["productId"] for p in body["plans"]} <= products
    assert body == TestClient(app).get("/api/studio/paypal").json()  # deterministic


def test_fixture_derived_columns():
    t = studio_paypal.paypal_tables()
    inv = {i["number"]: i for i in t["invoices"]}
    assert inv["PG-1006"]["daysOverdue"] == 97 and inv["PG-1006"]["agingBucket"] == "4. 90+ days"
    assert inv["PG-1008"]["issuedAmount"] == 0 and inv["PG-1008"]["isReceivable"] is False  # draft: nothing billed
    assert inv["PG-1005"]["daysOverdue"] == 0 and inv["PG-1005"]["agingBucket"] == "0. Not yet due"
    assert inv["PG-1007"]["netCollected"] == 520 and inv["PG-1001"]["daysToPay"] == 16
    assert [p["signedAmount"] for p in t["invoicePayments"] if p["kind"] == "Refund"] == [-120]
    plans = {p["name"]: p for p in t["plans"]}
    assert plans["Workspace Annual"]["monthlyPrice"] == pytest.approx(40.83) and plans["Workspace Monthly"]["trialDays"] == 14
    assert plans["Add-ons Quarterly"]["billingInterval"] == "Every 3 months" and plans["Add-ons Quarterly"]["monthlyPrice"] == 20
    assert {p["campaign"] for p in t["payouts"]} == {"Affiliates", "Creators", "Refunds"}
    assert studio_paypal._campaign(None) == "Other" and studio_paypal._campaign("INV-2026-1") == "Other"
    assert all(p["amount"] > 0 for p in t["payouts"]) and len(t["payouts"]) == 5
    assert t["balances"][0] == {"currency": "USD", "total": 9880.05, "available": 9380.05, "withheld": 500}


class MockAccount:
    """api-m.sandbox.paypal.com for one merchant: the fixture served the way PayPal pages and details it."""

    def __init__(self, fail_first_with: int | None = None):
        self.requests: list[httpx.Request] = []
        self.raw = studio_paypal.fixture_account()
        self.fail_first_with = fail_first_with

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        path, q = req.url.path, dict(req.url.params)
        if path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 32400})
        if self.fail_first_with and path == "/v1/reporting/balances":
            status, self.fail_first_with = self.fail_first_with, None
            return httpx.Response(status, json={"name": "RATE_LIMIT_REACHED", "message": "slow down"})

        def paged(items: list[dict], key: str, size: int) -> httpx.Response:
            assert int(q["page_size"]) == size
            start = (int(q["page"]) - 1) * 3  # 3 per page forces paging
            return httpx.Response(200, json={key: items[start : start + 3], "total_pages": -(-len(items) // 3)})

        for name, key in (("/v1/catalogs/products", "products"), ("/v1/billing/plans", "plans"), ("/v2/invoicing/invoices", "items")):
            if path == name:
                assert q["total_required"] == "true"
                return paged([{"id": r["id"]} for r in self.raw[key if key != "items" else "invoices"]], key, 20 if key != "items" else 100)
            if path.startswith(name + "/"):
                rows = self.raw[key if key != "items" else "invoices"]
                return httpx.Response(200, json=next(r for r in rows if r["id"] == path.rsplit("/", 1)[1]))
        if path == "/v1/reporting/transactions":
            return paged(self.raw["transactions"], "transaction_details", 500)
        if path == "/v1/reporting/balances":
            return httpx.Response(200, json=self.raw["balances"])
        return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND", "message": path})


def sandbox(mock: MockAccount) -> SandboxPayPal:
    gw = SandboxPayPal("cid", "secret", "https://api-m.sandbox.paypal.com")
    gw._http = httpx.Client(base_url="https://api-m.sandbox.paypal.com", transport=httpx.MockTransport(mock))
    return gw


def test_live_path_pages_fetches_details_and_matches_the_fixture():
    mock = MockAccount()
    now = datetime(2026, 11, 5, 12, 0, 0, 987654, tzinfo=UTC)  # microseconds must not reach PayPal
    live = studio_paypal.paypal_tables(sandbox(mock), now)
    assert live["source"] == "live"
    assert {k: v for k, v in live.items() if k != "source"} == {k: v for k, v in studio_paypal.paypal_tables().items() if k != "source"}
    txn = next(r for r in mock.requests if r.url.path == "/v1/reporting/transactions")
    assert txn.url.params["start_date"] == "2026-10-05T12:00:00Z" and txn.url.params["end_date"] == "2026-11-05T12:00:00Z"
    assert txn.url.params["fields"] == "all"
    details = [r.url.path for r in mock.requests if r.url.path.startswith("/v2/invoicing/invoices/")]
    assert len(details) == 8  # the list omits items and payments; each invoice is fetched in full
    assert sum(r.url.path == "/v1/oauth2/token" for r in mock.requests) == 1
    assert {r.headers["Authorization"] for r in mock.requests if r.url.path != "/v1/oauth2/token"} == {"Bearer tok"}


def test_live_read_retries_rate_limits(monkeypatch):
    monkeypatch.setattr("app.integrations.paypal.time.sleep", lambda s: None)
    mock = MockAccount(fail_first_with=429)
    assert studio_paypal.paypal_tables(sandbox(mock))["balances"]
    assert sum(r.url.path == "/v1/reporting/balances" for r in mock.requests) == 2


def test_endpoint_live_mode_serves_from_cache_and_maps_paypal_errors(monkeypatch):
    mock = MockAccount()
    monkeypatch.setattr(studio_paypal, "_gateway", lambda: sandbox(mock))
    studio_paypal._cache.clear()
    client = TestClient(app)
    first = client.get("/api/studio/paypal").json()
    n = len(mock.requests)
    assert first["source"] == "live" and client.get("/api/studio/paypal").json() == first
    assert len(mock.requests) == n  # second call inside the TTL made no PayPal request

    studio_paypal._cache.clear()
    monkeypatch.setattr(studio_paypal, "_gateway", lambda: sandbox(MockAccount(fail_first_with=403)))
    r = client.get("/api/studio/paypal")
    assert r.status_code == 502 and "RATE_LIMIT_REACHED" in r.json()["detail"]
    studio_paypal._cache.clear()


def test_non_retryable_errors_surface():
    with pytest.raises(PayPalAPIError) as e:
        studio_paypal.paypal_tables(sandbox(MockAccount(fail_first_with=403)))
    assert e.value.status == 403
