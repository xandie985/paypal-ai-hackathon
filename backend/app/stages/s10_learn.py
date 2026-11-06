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


def plan(ledger: EvidenceLedger, mandate: Mandate, mandate_lid: str) -> dict:
    """What calibration would do. Writes nothing, so the UI can preview it at any time."""
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

    new = None
    if changes:
        new = mandate.model_copy(
            update={
                "vendor_allowlist": allow,
                "auto_threshold": threshold,
                "version": mandate.version + 1,
                "parent_digest": mandate.digest(),
            }
        )
    return {"trust": trust, "changes": changes, "new": new}


def mandate_diff(before: dict, after: dict) -> list[dict]:
    """Field-level difference between two mandate versions, for the before/after view."""
    out = []
    for k in before:
        if k in ("version", "parent_digest") or before[k] == after.get(k):
            continue
        row = {"field": k, "before": before[k], "after": after.get(k)}
        if isinstance(before[k], list):
            row["removed"] = [x for x in before[k] if x not in after.get(k, [])]
            row["added"] = [x for x in after.get(k, []) if x not in before[k]]
        out.append(row)
    return out


def calibrate(ledger: EvidenceLedger, mandate: Mandate, mandate_lid: str) -> dict:
    p = plan(ledger, mandate, mandate_lid)
    trust, changes, new = p["trust"], p["changes"], p["new"]
    if new is None:
        return {"changed": False, "trust": trust, "mandate": mandate, "lineage_id": mandate_lid, "changes": []}
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


def calibrations(ledger: EvidenceLedger) -> list[dict]:
    """Every calibration already written to a ledger, newest first, with both mandate versions."""
    out = []
    for e in ledger.entries(kind="calibration"):
        before = ledger.latest(e.lineage_id, "mandate")
        after = ledger.latest(e.payload["next_mandate"], "mandate")
        if not before or not after:
            continue
        b, a = before.payload["mandate"], after.payload["mandate"]
        out.append(
            {
                "created_at": e.created_at,
                "from_lineage": e.lineage_id,
                "to_lineage": e.payload["next_mandate"],
                "changes": e.payload["changes"],
                "trust": e.payload["trust"],
                "before": b,
                "after": a,
                "diff": mandate_diff(b, a),
                "parent_digest_linked": a.get("parent_digest") == before.payload["digest"],
            }
        )
    return out[::-1]
