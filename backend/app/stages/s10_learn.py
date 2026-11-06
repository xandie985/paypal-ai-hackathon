"""Stage 10 - LEARN. Turns outcomes into a tighter (or looser) mandate.

Cold start: supplier trust is a Beta(2, 1) prior, so a new supplier starts trusted
but one lost dispute moves it a lot; per-user labels only refine it.
Rules (deliberately simple and explainable for the demo):
  - supplier trust < 0.5            -> removed from the allowlist
  - any lost dispute in the window  -> auto_threshold cut 25%
  - >= 5 approvals, 0 rejections    -> auto_threshold raised 10% (human is rubber-stamping)
The new mandate is a new version whose parent_digest links to the old one.
"""

from collections import defaultdict
from decimal import Decimal

from ..core.ledger import EvidenceLedger
from ..core.money import q
from ..domain.models import Mandate
from .s01_delegate import register_mandate

PRIOR_A, PRIOR_B = 2, 1


def trust_score(good: int, bad: int) -> float:
    """Beta(2, 1) prior: a new supplier starts trusted (0.667), and evidence moves it."""
    return round((PRIOR_A + good) / (PRIOR_A + PRIOR_B + good + bad), 3)


def supplier_trust(ledger: EvidenceLedger, prefix: str) -> dict[str, float]:
    good, bad = defaultdict(int), defaultdict(int)
    for e in ledger.entries(prefix, "dispute_outcome"):
        (good if e.payload["outcome"] == "WON" else bad)[e.payload["seller_id"]] += 1
    for e in ledger.entries(prefix, "delivery_proof"):
        seal = ledger.latest(e.lineage_id, "seal")
        if seal:
            (good if e.payload["verdict"] == "PASS" else bad)[seal.payload["seller_id"]] += 1
    return {s: trust_score(good[s], bad[s]) for s in set(good) | set(bad)}


def calibrate(ledger: EvidenceLedger, mandate: Mandate, mandate_lid: str) -> dict:
    trust = supplier_trust(ledger, mandate_lid)
    lost = [e for e in ledger.entries(mandate_lid, "dispute_outcome") if e.payload["outcome"] == "LOST"]
    approvals = len(ledger.entries(mandate_lid, "approval"))
    rejections = len(ledger.entries(mandate_lid, "rejection"))

    changes = []
    allow = [v for v in mandate.vendor_allowlist if trust.get(v, 1.0) >= 0.5]
    for v in set(mandate.vendor_allowlist) - set(allow):
        changes.append(f"removed {v} from allowlist (trust {trust[v]})")
    threshold = mandate.auto_threshold
    if lost:
        threshold = q(threshold * Decimal("0.75"))
        changes.append(f"auto_threshold {mandate.auto_threshold} -> {threshold} after {len(lost)} lost dispute(s)")
    elif approvals >= 5 and rejections == 0:
        threshold = q(threshold * Decimal("1.10"))
        changes.append(f"auto_threshold {mandate.auto_threshold} -> {threshold} ({approvals} approvals, 0 rejections)")

    if not changes:
        return {"changed": False, "trust": trust, "mandate": mandate, "lineage_id": mandate_lid, "changes": []}
    new = mandate.model_copy(
        update={"vendor_allowlist": allow, "auto_threshold": threshold, "version": mandate.version + 1, "parent_digest": mandate.digest()}
    )
    new_lid = register_mandate(ledger, new)
    ledger.append(mandate_lid, "10-learn", "calibration", {"trust": trust, "changes": changes, "next_mandate": new_lid})
    return {
        "changed": True,
        "trust": trust,
        "mandate": new,
        "lineage_id": new_lid,
        "changes": changes,
        "before": mandate.model_dump(mode="json"),
        "after": new.model_dump(mode="json"),
    }
