"""Channel3 product discovery.

Live: `POST /v1/search` with `x-api-key`; products carry `offers[]` (merchant `domain`,
`price.price`, `url`), `brands[]` and images. Channel3 does not expose return windows,
so `RETURN_POLICY_DAYS` supplies them for the merchants the demo queries return.
A merchant that isn't in the table (or is listed as None) keeps `return_days=None`:
the firewall's reversibility factor then fails and the purchase goes to a human.
That is the arXiv:2610.17378 "agent cannot decide on hidden terms" escalation.
"""

from decimal import Decimal, InvalidOperation
from typing import Protocol

import httpx

from ..domain.models import ProductCandidate


class ProductSource(Protocol):
    def search(self, query: str, category: str, limit: int = 10) -> list[ProductCandidate]: ...


# Standard return windows for electronics, as published by each retailer. Labelled demo data,
# not a live feed: re-check before recording. None = terms vary by seller, so treat as hidden.
RETURN_POLICY_DAYS: dict[str, int | None] = {
    "amazon.com": 30,
    "bestbuy.com": 15,
    "walmart.com": 30,
    "target.com": 30,
    "newegg.com": 30,
    "bhphotovideo.com": 30,
    "ebay.com": None,  # marketplace: each seller sets its own policy
    "adorama.com": None,  # feed does not expose return terms; routes to human
}

# Merchants the live demo queries return. DEMO_MANDATE's allowlist is built from these.
LIVE_DEMO_MERCHANTS = list(RETURN_POLICY_DAYS)


def normalize_domain(domain: str) -> str:
    d = domain.strip().lower().removeprefix("https://").removeprefix("http://").split("/")[0]
    return d.removeprefix("www.")


def return_days_for(merchant: str) -> int | None:
    return RETURN_POLICY_DAYS.get(normalize_domain(merchant))


REPLAY_CATALOG = [
    ("c3-mon-1", "27in 4K USB-C Monitor", "Northwind Displays", "monitors", "389.00", 30),
    ("c3-mon-2", "27in 4K IPS Monitor", "Contoso Retail", "monitors", "412.00", 30),
    ("c3-mon-3", "27in 4K Monitor (refurb)", "Fabrikam Outlet", "monitors", "301.00", None),
    ("c3-cam-1", "1080p Webcam with Privacy Shutter", "Contoso Retail", "webcams", "59.00", 30),
    ("c3-cam-2", "4K Streaming Webcam", "Northwind Displays", "webcams", "129.00", 14),
    ("c3-mic-1", "USB Condenser Microphone", "Contoso Retail", "microphones", "89.00", None),  # terms hidden on purpose
]


class ReplayChannel3:
    def search(self, query, category, limit=10):
        return [
            ProductCandidate(product_id=p, title=t, merchant=m, category=c, price=Decimal(pr), return_days=r, source="replay")
            for p, t, m, c, pr, r in REPLAY_CATALOG
            if c == category
        ][:limit]


class LiveChannel3:
    def __init__(self, api_key: str, base_url: str):
        self._http = httpx.Client(base_url=base_url, timeout=15, headers={"x-api-key": api_key})

    def search(self, query, category, limit=10):
        r = self._http.post("/v1/search", json={"query": query, "limit": limit})
        r.raise_for_status()
        found = (self._to_candidate(p, category) for p in r.json().get("products", []))
        return [c for c in found if c is not None]

    @staticmethod
    def _to_candidate(p: dict, category: str) -> ProductCandidate | None:
        """Map one Channel3 product. Returns None for a listing with no usable price, so a
        $0 placeholder can never become the cheapest pick or drag the baseline down."""
        offer = (p.get("offers") or [{}])[0]
        brand = ((p.get("brands") or [{}])[0] or {}).get("name")
        merchant = normalize_domain(offer["domain"]) if offer.get("domain") else (brand or "unknown")
        price_obj = offer.get("price") if isinstance(offer.get("price"), dict) else {}
        raw_price = price_obj.get("price") if price_obj else offer.get("price", p.get("price"))
        try:
            price = Decimal(str(raw_price).replace("$", "").replace(",", "").strip())
        except (InvalidOperation, TypeError):
            return None
        if not price.is_finite() or price <= 0:
            return None
        images = p.get("images") or [{}]
        return ProductCandidate(
            product_id=str(p.get("id")),
            title=p.get("title", ""),
            merchant=merchant,
            category=category,
            price=price,
            currency=price_obj.get("currency") or "USD",
            return_days=return_days_for(merchant),
            url=offer.get("url", ""),
            image_url=p.get("image_url") or (images[0] or {}).get("url", ""),
            source="channel3",
        )


def make_product_source(settings) -> ProductSource:
    if not settings.replay_mode and settings.channel3_api_key:
        return LiveChannel3(settings.channel3_api_key, settings.channel3_base_url)
    return ReplayChannel3()
