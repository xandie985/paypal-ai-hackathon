"""Idempotency evaluation: every money-moving call is retried; count the real side effects.

The replay gateway mirrors PayPal's PayPal-Request-Id behaviour (a repeated id returns the original result and does
nothing new) and records each real side effect, so a retry that would have charged or paid twice is visible.

    python -m eval.idempotency_runs
"""

from decimal import Decimal

from app.core.gates import RECONCILED, VERIFIED, issue
from app.core.ledger import EvidenceLedger
from app.core.lineage import request_id
from app.integrations.paypal import ReplayPayPal
from app.stages import s07_payout

RETRIES = 10
SECRET = "eval-secret"
LID = "PG-evalevaleval0001.0000000001"
PURCHASE_UNIT = {"amount": {"currency_code": "USD", "value": "118.00"}, "custom_id": LID}


def run() -> dict:
    gw = ReplayPayPal()
    rid = lambda op, *p: request_id(LID, "eval", op, *p)  # noqa: E731
    # Fixtures use their own request ids, so the measured calls below start from a clean slate.
    order_id = gw.create_order(PURCHASE_UNIT, rid("setup-order"))["id"]
    invoice_id = gw.create_invoice({"detail": {"invoice_number": "NW-0"}}, rid("setup-invoice"))["id"]
    gw.calls.clear()

    operations = {
        "create_order": lambda: gw.create_order(PURCHASE_UNIT, rid("order")),
        "capture_order": lambda: gw.capture_order(order_id, rid("capture")),
        "create_invoice": lambda: gw.create_invoice({"detail": {"invoice_number": "NW-1"}}, rid("invoice")),
        "send_invoice": lambda: gw.send_invoice(invoice_id, rid("send")),
        "remind_invoice": lambda: gw.remind_invoice(invoice_id, rid("remind")),
    }
    ledger = EvidenceLedger(":memory:")
    verified, reconciled = issue(SECRET, VERIFIED, LID, order_id), issue(SECRET, RECONCILED, LID, "NW-1")
    operations["release_payout (stage 7)"] = lambda: s07_payout.release_payout(
        ledger, gw, SECRET, LID, order_id=order_id, invoice_number="NW-1", payee_email="ar@contoso.example",
        gross=Decimal("118"), verified_token=verified, reconciled_token=reconciled,
    )  # fmt: skip

    rows = {}
    for name, call in operations.items():
        before = len(gw.calls)
        results = [call() for _ in range(RETRIES)]
        op = name.split(" ")[0].replace("release_payout", "create_payout")
        rows[name] = {
            "attempts": RETRIES,
            "side_effects": sum(1 for o, _ in gw.calls[before:] if o == op),
            "same_result": all(r == results[0] for r in results),
        }
    # A different logical operation (another invoice number) must still go through: idempotency is not suppression.
    fresh = gw.create_invoice({"detail": {"invoice_number": "NW-2"}}, rid("invoice", "NW-2"))
    return {"retries": RETRIES, "operations": rows, "distinct_operation_allowed": fresh["id"] not in (invoice_id, rows_invoice_id(gw))}


def rows_invoice_id(gw: ReplayPayPal) -> str:
    """The invoice the measured create_invoice produced (same request id as every retry)."""
    return gw.create_invoice({"detail": {"invoice_number": "NW-1"}}, request_id(LID, "eval", "invoice"))["id"]


def table(res: dict) -> str:
    lines = ["| Operation | Attempts | Real side effects | Same result every time |", "|---|---:|---:|---|"]
    for name, r in res["operations"].items():
        lines.append(f"| {name} | {r['attempts']} | {r['side_effects']} | {'yes' if r['same_result'] else 'NO'} |")
    return "\n".join(lines)


if __name__ == "__main__":
    print(table(run()))
