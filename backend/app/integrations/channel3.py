"""Channel3 product discovery.

UNVERIFIED: the live endpoint path, auth header and response field names below are
placeholders until we read the Channel3 docs (docs host was unreachable from the
build sandbox). Everything Channel3-specific is confined to `_to_candidate` and
`LiveChannel3.search`, so fixing the shape is a one-file change.
"""

from decimal import Decimal
from typing import Protocol

import httpx

from ..domain.models import ProductCandidate


class ProductSource(Protocol):
    def search(self, query: str, category: str, limit: int = 10) -> list[ProductCandidate]: ...


REPLAY_CATALOG = [
    ("c3-mon-1", "27in 4K USB-C Monitor", "Northwind Displays", "monitors", "389.00", 30),
    ("c3-mon-2", "27in 4K IPS Monitor", "Contoso Retail", "monitors", "412.00", 30),
    ("c3-mon-3", "27in 4K Monitor (refurb)", "Fabrikam Outlet", "monitors", "301.00", None),
    ("c3-cam-1", "1080p Webcam with Privacy Shutter", "Contoso Retail", "webcams", "59.00", 30),
    ("c3-cam-2", "4K Streaming Webcam", "Northwind Displays", "webcams", "129.00", 14),
    ("c3-mic-1", "USB Condenser Microphone", "Contoso Retail", "microphones", "89.00", 30),
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
        return [self._to_candidate(p, category) for p in r.json().get("products", [])]

    @staticmethod
    def _to_candidate(p: dict, category: str) -> ProductCandidate:
        offers = p.get("offers") or [{}]
        offer = offers[0] if offers else {}
        brand = (p.get("brands") or [{}])[0].get("name") if p.get("brands") else None
        merchant = offer.get("domain") or brand or "unknown"
        price_val = offer.get("price", {}).get("price") if offer.get("price") else p.get("price", "0")
        return ProductCandidate(
            product_id=str(p.get("id")),
            title=p.get("title", ""),
            merchant=merchant,
            category=category,
            price=Decimal(str(price_val)),
            return_days=None,  # Channel3 does not expose return windows; firewall routes to human on hidden terms
            url=offer.get("url", ""),
            source="channel3",
        )


def make_product_source(settings) -> ProductSource:
    if not settings.replay_mode and settings.channel3_api_key:
        return LiveChannel3(settings.channel3_api_key, settings.channel3_base_url)
    return ReplayChannel3()
