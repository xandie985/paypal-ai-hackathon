"""Stage 9 - OBSERVE. Flattens the ledger into row data for AG Grid / AG Studio.
One row per transaction lineage; columns are stable so Studio widgets can bind to them."""

from collections import defaultdict
from decimal import Decimal

from ..core.ledger import EvidenceLedger


def transaction_rows(ledger: EvidenceLedger, lineage_prefix: str | None = None) -> list[dict]:
    """`lineage_prefix` = a run's mandate lineage: live runs share one ledger file."""
    by_lid: dict[str, dict] = defaultdict(dict)
    for e in ledger.entries(lineage_prefix):
        if "." not in e.lineage_id:
            continue
        r = by_lid[e.lineage_id]
        r["lineage_id"] = e.lineage_id
        p = e.payload
        if e.kind == "decision":
            prop = p["proposal"]
            base = prop.get("baseline_unit_price")
            r.update(
                vendor=prop["vendor"],
                category=prop["category"],
                action=prop["action"],
                route=p["route"],
                amount=str(Decimal(prop["unit_price"]) * prop["quantity"]),
                firewall_ms=p["latency_ms"],
                blocked_reasons="; ".join(p["reasons"]) if p["route"] == "BLOCKED" else "",
            )
            if base:
                r["savings"] = str((Decimal(base) - Decimal(prop["unit_price"])) * prop["quantity"])
        elif e.kind == "approval":
            r["approved_by"] = p["approver"]
        elif e.kind == "seal":
            r["order_id"] = p.get("order_id", "")
        elif e.kind == "capture":
            r["status"] = "CAPTURED"
            r["order_id"] = p.get("order_id") or r.get("order_id", "")
            r["capture_id"] = p.get("capture_id", "")
        elif e.kind == "delivery_proof":
            r["delivery"] = p["verdict"]
        elif e.kind == "reconciliation":
            r["invoice_status"] = p["status"]
        elif e.kind == "payout":
            r["payout_net"] = p["net"]
        elif e.kind == "dispute_response":
            r["dispute_win_odds"] = p["win_odds"]
        elif e.kind == "dispute_outcome":
            r["dispute_outcome"] = p["outcome"]
    return list(by_lid.values())


def kpis(rows: list[dict]) -> dict:
    routes = [r.get("route") for r in rows]
    return {
        "transactions": len(rows),
        "auto_settled": routes.count("AUTO_SETTLE"),
        "human_approved": routes.count("HUMAN_APPROVAL"),
        "blocked": routes.count("BLOCKED"),
        "total_savings": str(sum((Decimal(r["savings"]) for r in rows if r.get("savings") and r.get("route") != "BLOCKED"), Decimal("0"))),
        "disputes_won": sum(r.get("dispute_outcome") == "WON" for r in rows),
        "disputes_lost": sum(r.get("dispute_outcome") == "LOST" for r in rows),
    }
