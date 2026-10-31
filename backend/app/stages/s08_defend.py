"""Stage 8 - DEFEND. The toolkit can only accept_dispute_claim (surrender). We
answer disputes from records sealed *before* the dispute existed: the seal (terms,
price, SKU, return policy, buyer IP), the delivery proof, and the chain of hashes
that shows none of it was edited afterwards.
"""

import io
from datetime import date

from ..core.ledger import EvidenceLedger
from ..domain.models import Dispute
from ..integrations.paypal import PayPalGateway

STAGE = "8-defend"

# What each reason needs to be winnable, and which ledger kinds supply it.
REQUIRED = {
    "MERCHANDISE_OR_SERVICE_NOT_RECEIVED": ["seal", "delivery_proof"],
    "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED": ["seal", "delivery_proof", "decision"],
    "UNAUTHORISED": ["seal", "decision", "approval"],
}


def build_evidence(ledger: EvidenceLedger, dispute: Dispute) -> dict:
    lid = dispute.lineage_id
    found = {kind: ledger.latest(lid, kind) for kind in ("mandate", "decision", "approval", "seal", "delivery_proof", "capture")}
    if found["mandate"] is None:  # mandate lives on the parent lineage
        found["mandate"] = ledger.latest(lid.split(".")[0], "mandate")
    proof = found["delivery_proof"]
    delivered = bool(proof and proof.payload["verdict"] == "PASS")
    needed = REQUIRED[dispute.reason]
    # A delivery proof that says FAIL/LATE is evidence against us, not for us.
    missing = [k for k in needed if found.get(k) is None or (k == "delivery_proof" and not delivered)]
    chain_ok, _ = ledger.verify()

    score = 0.1 + 0.7 * (len(needed) - len(missing)) / len(needed) + (0.1 if delivered else 0) + (0.1 if chain_ok else -0.3)
    if dispute.reason == "MERCHANDISE_OR_SERVICE_NOT_RECEIVED" and not delivered:
        score = min(score, 0.15)
    seal = found["seal"].payload if found["seal"] else {}
    evidence = {
        "evidences": [
            {
                "evidence_type": "PROOF_OF_FULFILLMENT" if delivered else "OTHER",
                "evidence_info": {
                    "tracking_info": [{"carrier_name": proof.payload["carrier"], "tracking_number": proof.payload["tracking_number"]}]
                    if delivered
                    else []
                },
                "notes": (
                    f"Order {seal.get('order_id')} sealed at checkout with terms hash {seal.get('terms_hash', '')[:16]}..., "
                    f"return window {seal.get('return_days')} days, buyer IP {seal.get('buyer_ip')}. "
                    f"Delivery verdict: {proof.payload['verdict'] if proof else 'none'}. Ledger chain intact: {chain_ok}."
                )[:2000],
            }
        ]
    }
    return {
        "lineage_id": lid,
        "records": {k: (v.payload | {"entry_hash": v.entry_hash, "seq": v.seq}) if v else None for k, v in found.items()},
        "missing": missing,
        "chain_ok": chain_ok,
        "win_odds": round(max(0.0, min(score, 0.95)), 2),
        "paypal_evidence": evidence,
    }


def render_pdf(dispute: Dispute, bundle: dict) -> bytes:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    y = 750

    def line(text, size=10):
        nonlocal y
        c.setFont("Helvetica", size)
        c.drawString(50, y, text[:110])
        y -= size + 6

    line(f"Dispute {dispute.dispute_id} - evidence brief", 14)
    line(f"Reason: {dispute.reason}   Amount: {dispute.amount}   Lineage: {dispute.lineage_id}")
    line(f"Ledger chain verified: {bundle['chain_ok']}   Missing records: {bundle['missing'] or 'none'}")
    for kind, rec in bundle["records"].items():
        if rec:
            line(f"[{kind}] seq {rec['seq']} hash {rec['entry_hash'][:24]}...", 11)
            for k, v in rec.items():
                if k not in ("seq", "entry_hash") and not isinstance(v, (dict, list)):
                    line(f"    {k}: {v}")
        if y < 80:
            c.showPage()
            y = 750
    c.save()
    return buf.getvalue()


def submit(ledger: EvidenceLedger, gateway: PayPalGateway, dispute: Dispute, bundle: dict) -> dict:
    pdf = render_pdf(dispute, bundle)
    resp = gateway.provide_evidence(dispute.dispute_id, bundle["paypal_evidence"], [(f"{dispute.dispute_id}-brief.pdf", pdf)])
    ledger.append(
        dispute.lineage_id,
        STAGE,
        "dispute_response",
        {"dispute_id": dispute.dispute_id, "reason": dispute.reason, "win_odds": bundle["win_odds"], "missing": bundle["missing"]},
    )
    return resp


def record_outcome(ledger: EvidenceLedger, dispute: Dispute, outcome: str, seller_id: str) -> None:
    """WON / LOST label that stage 10 learns from."""
    ledger.append(
        dispute.lineage_id, STAGE, "dispute_outcome", {"dispute_id": dispute.dispute_id, "outcome": outcome, "seller_id": seller_id}
    )


def triage(disputes: list[Dispute], odds: dict[str, float], today: date) -> list[dict]:
    rows = [
        {
            "dispute_id": d.dispute_id,
            "days_left": (date.fromisoformat(d.seller_response_due_date) - today).days,
            "win_odds": odds.get(d.dispute_id, 0.0),
            "amount": str(d.amount),
        }
        for d in disputes
    ]
    return sorted(rows, key=lambda r: (r["days_left"], -r["win_odds"]))
