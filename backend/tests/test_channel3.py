"""Live Channel3 mapping, run against a recorded /v1/search payload (no network)."""

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.domain.models import Mandate, Need
from app.integrations.channel3 import RETURN_POLICY_DAYS, LiveChannel3, normalize_domain, return_days_for
from app.orchestrator import DEMO_MANDATE
from app.stages import s02_discover

PAYLOAD = json.loads((Path(__file__).parent / "fixtures" / "channel3_search.json").read_text())


def mapped() -> dict:
    out = {}
    for p in PAYLOAD["products"]:
        c = LiveChannel3._to_candidate(p, "webcams")
        out[p["id"]] = c
    return out


def test_live_channel3_mapping():
    m = mapped()
    cam = m["prod_webcam_1"]
    # First offer wins; domain is normalized; price is a Decimal; known merchant gets its return window.
    assert cam.merchant == "amazon.com" and cam.price == Decimal("59.99") and cam.currency == "USD"
    assert cam.return_days == 30 and cam.url.startswith("https://www.amazon.com/")
    assert cam.image_url == "https://img.example/c920.jpg" and cam.source == "channel3" and cam.category == "webcams"

    ebay = m["prod_webcam_2"]
    assert ebay.price == Decimal("1024.50")  # "$1,024.50" string
    assert ebay.return_days is None  # marketplace: terms hidden on purpose
    assert ebay.image_url == "https://img.example/generic.jpg"  # images[] fallback

    brand_only = m["prod_webcam_3"]
    assert brand_only.merchant == "Razer" and brand_only.price == Decimal("79.00")  # no offers: brand + top-level price
    assert brand_only.return_days is None and brand_only.image_url == ""

    unknown = m["prod_webcam_4"]
    assert unknown.merchant == "shop.unknown-merchant.example" and unknown.return_days is None

    assert m["prod_scalar_price"].price == Decimal("129.95") and m["prod_scalar_price"].return_days == 30


def test_listings_without_a_usable_price_are_dropped():
    m = mapped()
    assert m["prod_no_price"] is None and m["prod_zero"] is None


def test_search_filters_unpriced_listings(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/search" and request.headers["x-api-key"] == "k"
        assert json.loads(request.content) == {"query": "1080p webcam", "limit": 10}
        return httpx.Response(200, json=PAYLOAD)

    src = LiveChannel3("k", "https://api.example")
    src._http = httpx.Client(base_url="https://api.example", headers={"x-api-key": "k"}, transport=httpx.MockTransport(handler))
    found = src.search("1080p webcam", "webcams")
    assert len(found) == 5 and all(c.price > 0 for c in found)


@pytest.mark.parametrize(
    "raw,norm",
    [("www.Amazon.com", "amazon.com"), ("https://www.bestbuy.com/site/x", "bestbuy.com"), ("ebay.com", "ebay.com")],
)
def test_normalize_domain(raw, norm):
    assert normalize_domain(raw) == norm


def test_return_policy_lookup():
    assert return_days_for("www.amazon.com") == 30
    assert return_days_for("bestbuy.com") == 15  # under the 30-day minimum: reversibility fails, human review
    assert return_days_for("ebay.com") is None and return_days_for("nobody.example") is None


def test_demo_allowlist_covers_live_merchants():
    assert set(RETURN_POLICY_DAYS) <= set(DEMO_MANDATE.vendor_allowlist)
    assert {"Northwind Displays", "Contoso Retail"} <= set(DEMO_MANDATE.vendor_allowlist)  # simulated negotiators


def test_live_candidates_flow_through_discovery():
    class Fixed:
        def search(self, query, category, limit=10):
            return [c for c in mapped().values() if c is not None]

    found = s02_discover.discover(Fixed(), DEMO_MANDATE, Need(description="1080p webcam", category="webcams", quantity=2))
    assert found["baseline_unit_price"] == Decimal("79.00")  # median of 45.10, 59.99, 79.00, 129.95, 1024.50
    allowed = {c.merchant for c in found["allowlisted"]}
    assert allowed == {"amazon.com", "ebay.com", "newegg.com"}  # Razer brand and the unknown shop are not allowlisted
    assert set(found["hidden_terms"]) == {"prod_webcam_2", "prod_webcam_3", "prod_webcam_4"}
    assert isinstance(DEMO_MANDATE, Mandate)
