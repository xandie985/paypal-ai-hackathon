"""Stage 2a - DISCOVER. Product graph lookup (Channel3) to get a retail baseline and
return terms before any negotiation. The baseline anchors the firewall's price factor."""

from decimal import Decimal
from statistics import median

from ..domain.models import Mandate, Need, ProductCandidate
from ..integrations.channel3 import ProductSource


def discover(source: ProductSource, mandate: Mandate, need: Need) -> dict:
    candidates: list[ProductCandidate] = source.search(need.description, need.category)
    if not candidates:
        return {"candidates": [], "baseline_unit_price": None, "hidden_terms": []}
    baseline = Decimal(str(median(c.price for c in candidates)))
    return {
        "candidates": candidates,
        "baseline_unit_price": baseline,
        # Blocker B2a: a merchant that hides its return window can't be auto-settled.
        "hidden_terms": [c.product_id for c in candidates if c.return_days is None],
        "allowlisted": [c for c in candidates if c.merchant in mandate.vendor_allowlist],
    }
