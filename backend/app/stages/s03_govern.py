"""Stage 3 - GOVERN. The 4-factor Mandate Firewall sits in front of every money
movement (orders AND payouts), because the PayPal agent toolkit has no spend cap.

Factors: Warrant (is this authorized at all), Reversibility (can we undo it),
Price (is it in line with the discovery baseline), Budget (does it fit).
Hard failures BLOCK; soft failures route to a human; otherwise AUTO_SETTLE.
"""

import re
import time
from decimal import Decimal

from ..core.canonical import sha256_hex
from ..core.gates import APPROVED, issue
from ..core.ledger import EvidenceLedger
from ..core.lineage import request_id
from ..domain.models import Decision, FactorResult, Mandate, Proposal

STAGE = "3-govern"

INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) (instructions|rules)",
    r"\bsystem\s*:",
    r"you are now",
    r"(send|transfer|wire|pay ?out|refund)\b.{0,40}\b(to|into)\b.{0,40}(@|account|wallet)",
    r"(override|bypass|disable).{0,20}(mandate|firewall|limit|approval)",
    r"approve (this|immediately|automatically)",
    # Paraphrases. Tripwires, not a guarantee: seller text never changes a route except to BLOCK it, so a phrasing
    # that slips past can only auto-settle a purchase that independently passes all four numeric factors.
    r"\b(disregard|forget|ignore)\b.{0,40}\b(earlier|previous|prior|above|preceding)\b",
    r"\bpre-?(approved|authori[sz]ed)\b",
    r"\b(skip|bypass)\b.{0,25}\b(approval|review|checks?|limits?)\b",
    r"\bwithout\b.{0,12}\b(approval|review)\b",
    r"\bnew polic(y|ies)\b",
]
_INJ = [re.compile(p, re.I) for p in INJECTION_PATTERNS]


def scan_injection(texts: list[str]) -> list[str]:
    return [p.pattern for t in texts for p in _INJ if p.search(t)]


def evaluate(ledger: EvidenceLedger, mandate: Mandate, p: Proposal, spent: Decimal) -> Decision:
    t0 = time.perf_counter()
    hits = scan_injection(p.untrusted_text)

    warrant_problems = []
    if hits:
        warrant_problems.append(f"prompt-injection markers in untrusted text ({len(hits)})")
    if p.vendor not in mandate.vendor_allowlist:
        warrant_problems.append(f"vendor {p.vendor!r} not on allowlist")
    if p.category not in mandate.allowed_categories:
        warrant_problems.append(f"category {p.category!r} not allowed")
    if p.action == "payout" and p.origin == "agent_tool_call":
        warrant_problems.append("payouts are only issued by the Payout stage, never by an agent tool call")

    rev_ok = p.return_days is not None and p.return_days >= mandate.min_return_days
    rev_detail = "return terms hidden" if p.return_days is None else f"{p.return_days}d vs {mandate.min_return_days}d required"

    if p.baseline_unit_price:
        premium = (p.unit_price - p.baseline_unit_price) / p.baseline_unit_price * 100
        price_ok = premium <= mandate.max_price_premium_pct
        price_detail = f"{premium:.1f}% vs baseline (max {mandate.max_price_premium_pct}%)"
    else:
        price_ok, price_detail = False, "no baseline"

    total = p.total
    budget_ok = spent + total <= mandate.budget and total <= mandate.per_txn_cap
    budget_detail = f"{total} + spent {spent} vs budget {mandate.budget}, cap {mandate.per_txn_cap}"

    factors = [
        FactorResult(name="warrant", passed=not warrant_problems, hard=True, detail="; ".join(warrant_problems) or "authorized"),
        FactorResult(name="reversibility", passed=rev_ok, hard=False, detail=rev_detail),
        FactorResult(name="price", passed=price_ok, hard=False, detail=price_detail),
        FactorResult(name="budget", passed=budget_ok, hard=True, detail=budget_detail),
    ]

    reasons = [f"{f.name}: {f.detail}" for f in factors if not f.passed]
    if any(not f.passed and f.hard for f in factors):
        route = "BLOCKED"
    elif reasons or total > mandate.auto_threshold or mandate.mode == "review_first":
        route = "HUMAN_APPROVAL"
        if total > mandate.auto_threshold:
            reasons.append(f"total {total} over auto threshold {mandate.auto_threshold}")
        if mandate.mode == "review_first":
            reasons.append("mandate is review-first")
    else:
        route = "AUTO_SETTLE"

    digest = sha256_hex(
        {"mandate": mandate.digest(), "proposal": p.model_dump(mode="json"), "route": route, "factors": [f.model_dump() for f in factors]}
    )
    decision = Decision(
        lineage_id=p.lineage_id,
        route=route,
        factors=factors,
        reasons=reasons,
        decision_digest=digest,
        request_id=request_id(p.lineage_id, "s3", "decision", digest),
        latency_ms=round((time.perf_counter() - t0) * 1000, 3),
    )
    ledger.append(p.lineage_id, STAGE, "decision", {"proposal": p.model_dump(mode="json"), **decision.model_dump(mode="json")})
    return decision


def approve(ledger: EvidenceLedger, secret: str, decision: Decision, approver: str) -> str:
    """Human 1-click approval. Only HUMAN_APPROVAL decisions can be approved; BLOCKED stays blocked."""
    if decision.route != "HUMAN_APPROVAL":
        raise ValueError(f"cannot approve a {decision.route} decision")
    ledger.append(decision.lineage_id, STAGE, "approval", {"decision_digest": decision.decision_digest, "approver": approver})
    return issue(secret, APPROVED, decision.lineage_id, decision.decision_digest)


def reject(ledger: EvidenceLedger, decision: Decision, approver: str, reason: str) -> None:
    ledger.append(
        decision.lineage_id, STAGE, "rejection", {"decision_digest": decision.decision_digest, "approver": approver, "reason": reason}
    )
