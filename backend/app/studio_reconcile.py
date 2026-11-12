"""Agent-to-PayPal reconciliation for the Command Center: did the money the agent decided to move show up in
the PayPal account's own ledger? One row per captured agent purchase (matched on `capture_id`), plus the purchase
captures PayPal shows that the agent never decided. Derived here, not in the browser, so it is tested and the
assistant reads the same table the page does."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter

from . import runs
from .api import studio_rows
from .studio_paypal import FIXTURE_AS_OF, build_tables, fixture_account, studio_paypal

router = APIRouter(prefix="/api")

SEARCH_WINDOW = timedelta(days=31)  # Transaction Search cannot see further back than this
INDEX_LAG = timedelta(hours=3)  # a fresh capture can take a while to appear in Transaction Search
TOLERANCE = 0.005

# The two event codes an agent capture shows up as: a checkout capture, or a vaulted (saved-wallet) one. Live sandbox
# captures are credits to the merchant account, so direction is not part of the test.
PURCHASE_CAPTURES = {"Purchase capture", "Pre-approved payment"}

NOTES = {
    "Matched": "PayPal shows this capture for the same amount.",
    "Amount mismatch": "PayPal shows this capture, but for a different amount than the agent sealed.",
    "Pending": "Captured within the last few hours; Transaction Search may not have indexed it yet.",
    "Outside window": "Older than the 31 days Transaction Search covers, so it cannot be checked here.",
    "Unsettled": "No PayPal transaction with this capture ID inside the search window.",
    "Simulated": "A simulated purchase (seeded history or replay): no PayPal object exists for it.",
    "Sandbox capture": (
        "A real capture in the PayPal sandbox. This deployment reads a fixed fixture instead of the account, "
        "so it cannot be matched here; check the sandbox account's Activity."
    ),
    "Not decided by agent": "A purchase capture in the PayPal account with no agent decision behind it.",
}


def _when(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _agent_row(r: dict, txn: dict | None, source: str, as_of: datetime) -> dict:
    amount = float(r["amount"]) if r.get("amount") not in (None, "") else None
    created = _when(r.get("created_at"))
    if txn is not None:
        paid = abs(float(txn["amount"]))
        same = amount is not None and abs(paid - amount) <= TOLERANCE and txn.get("currency") in (None, "USD")
        status = "Matched" if same else "Amount mismatch"
    elif r.get("sandbox") and source == "replay":
        status = "Sandbox capture"  # real, but the replay fixture cannot contain it
    elif r.get("source") == "seeded" or source == "replay":
        status = "Simulated"
    elif created and created < as_of - SEARCH_WINDOW:
        status = "Outside window"
    elif created and as_of - created < INDEX_LAG:
        status = "Pending"
    else:
        status = "Unsettled"
    paypal_amount = abs(float(txn["amount"])) if txn else None
    return {
        "id": r["capture_id"],
        "lineageId": r["lineage_id"],
        "origin": r.get("source"),
        "vendor": r.get("vendor"),
        "category": r.get("category"),
        "date": r.get("created_at"),
        "agentAmount": amount,
        "paypalAmount": paypal_amount,
        "paypalFee": abs(float(txn["fee"])) if txn else None,
        "netCash": float(txn["net"]) if txn else None,
        "difference": round(paypal_amount - amount, 2) if paypal_amount is not None and amount is not None else None,
        "status": status,
        "note": NOTES[status],
        "paypalId": txn["id"] if txn else None,
    }


def _orphan_row(txn: dict) -> dict:
    return {
        "id": txn["id"],
        "lineageId": None,
        "origin": None,
        "vendor": txn.get("counterparty"),
        "category": None,
        "date": txn.get("date"),
        "agentAmount": None,
        "paypalAmount": abs(float(txn["amount"])),
        "paypalFee": abs(float(txn["fee"])),
        "netCash": float(txn["net"]),
        "difference": None,
        "status": "Not decided by agent",
        "note": NOTES["Not decided by agent"],
        "paypalId": txn["id"],
    }


def reconcile(agent_rows: list[dict], transactions: list[dict], source: str, as_of: datetime) -> list[dict]:
    """Newest first. `source` is the PayPal data mode, "live" or "replay"."""
    by_id = {t["id"]: t for t in transactions}
    captured = [r for r in agent_rows if r.get("capture_id") and r.get("status") == "CAPTURED"]
    rows = [_agent_row(r, by_id.get(r["capture_id"]), source, as_of) for r in captured]
    seen = {r["capture_id"] for r in captured}
    rows += [_orphan_row(t) for t in transactions if t["eventType"] in PURCHASE_CAPTURES and t["id"] not in seen]
    rows.sort(key=lambda r: r["date"] or "", reverse=True)
    return rows


def summarise(rows: list[dict]) -> dict:
    count = lambda s: sum(r["status"] == s for r in rows)  # noqa: E731
    return {
        "captures": sum(r["lineageId"] is not None for r in rows),
        "matched": count("Matched"),
        "mismatched": count("Amount mismatch"),
        "simulated": count("Simulated"),
        "sandboxCaptures": count("Sandbox capture"),
        "pending": count("Pending"),
        "unsettled": count("Unsettled"),
        "outsideWindow": count("Outside window"),
        "notDecidedByAgent": count("Not decided by agent"),
        "fees": round(sum(r["paypalFee"] or 0 for r in rows), 2),
        "netCash": round(sum(r["netCash"] or 0 for r in rows), 2),
    }


@router.get("/studio/reconciliation")
def studio_reconciliation(run_id: str | None = None, fixture: bool = False):
    """Agent captures against the PayPal account ledger. A plain `def`: the live PayPal read blocks."""
    paypal = {"source": "replay", **build_tables(fixture_account(), FIXTURE_AS_OF)} if fixture else studio_paypal()
    agent_rows = studio_rows(run_id, history=True)["rows"]
    # The row contract is frozen, so a sandbox run is marked here rather than as a Studio column.
    sandbox = {i.lineage_id for run in runs.RUNS.values() if run.sandbox for i in run.items.values()}
    agent_rows = [{**r, "sandbox": r["lineage_id"] in sandbox} for r in agent_rows]
    rows = reconcile(agent_rows, paypal["transactions"], paypal["source"], _when(paypal["asOf"]))
    return {"source": paypal["source"], "asOf": paypal["asOf"], "rows": rows, "summary": summarise(rows)}
