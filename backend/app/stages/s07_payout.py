"""Stage 7 - PAY OUT and COLLECT.

Payout releases supplier funds only with BOTH gate tokens: VERIFIED (stage 5) and
RECONCILED (stage 6). The toolkit has no Payouts tool, so this calls Payouts v1
directly; sender_batch_id is derived from the lineage, and PayPal rejects a reused
sender_batch_id, which gives us a second layer of idempotency.

Webhooks are verified, de-duplicated by event id, stored, and replayable, because
sandbox events arrive late, twice, or not at all.
"""

import threading
from datetime import date
from decimal import Decimal

from ..core.errors import WebhookUnverified
from ..core.gates import RECONCILED, VERIFIED, require
from ..core.ledger import EvidenceLedger, LedgerEntry
from ..core.lineage import request_id
from ..core.money import gross_to_net
from ..integrations.paypal import PayPalGateway

STAGE = "7-payout"


def release_payout(
    ledger: EvidenceLedger,
    gateway: PayPalGateway,
    secret: str,
    lineage_id: str,
    *,
    order_id: str,
    invoice_number: str,
    payee_email: str,
    gross: Decimal,
    verified_token: str | None,
    reconciled_token: str | None,
    fee_pct: Decimal = Decimal("0.02"),
    fee_fixed: Decimal = Decimal("0.25"),
    currency: str = "USD",
) -> dict:
    require(secret, verified_token, VERIFIED, lineage_id, order_id)
    require(secret, reconciled_token, RECONCILED, lineage_id, invoice_number)
    split = gross_to_net(gross, fee_pct, fee_fixed)
    sender_batch_id = f"{lineage_id}-{invoice_number}"[:127]
    batch = {
        "sender_batch_header": {"sender_batch_id": sender_batch_id, "email_subject": "Payment released"},
        "items": [
            {
                "recipient_type": "EMAIL",
                "receiver": payee_email,
                "amount": {"currency": currency, "currency_code": currency, "value": format(split["net"], "f")},
                "note": f"Lineage {lineage_id}",
                "sender_item_id": invoice_number[:63],
            }
        ],
    }
    resp = gateway.create_payout(batch, request_id(lineage_id, "s7", "payout", invoice_number))
    ledger.append(
        lineage_id,
        STAGE,
        "payout",
        {
            "sender_batch_id": sender_batch_id,
            "payee": payee_email,
            **{k: str(v) for k, v in split.items()},
            "response": resp["batch_header"],
        },
    )
    return {"split": split, "batch_header": resp["batch_header"]}


class WebhookInbox:
    """Verify, then de-duplicate by event id, then store. The ledger is the store, so a redelivery after a
    restart is still caught and every accepted event can be replayed from the sealed record."""

    def __init__(self, ledger: EvidenceLedger, gateway: PayPalGateway):
        self.ledger, self.gateway = ledger, gateway
        self._lock = threading.Lock()  # two deliveries of one event must not both pass the duplicate check

    def _stored(self) -> dict[str, LedgerEntry]:
        return {e.payload["event_id"]: e for e in self.ledger.entries(kind="webhook") if "event" in e.payload}

    def receive(self, headers: dict, body: dict, raw: bytes | None = None) -> dict:
        if not self.gateway.verify_webhook(headers, body, raw):
            raise WebhookUnverified("webhook signature verification failed", event_id=body.get("id"))
        eid = body["id"]
        resource = body.get("resource", {})
        lid = resource.get("custom_id") or resource.get("detail", {}).get("reference") or "unlinked"
        with self._lock:
            if eid in self._stored():
                return {"event_id": eid, "duplicate": True}
            self.ledger.append(lid, STAGE, "webhook", {"event_id": eid, "event_type": body.get("event_type"), "event": body})
        return {"event_id": eid, "duplicate": False, "lineage_id": lid}

    def replay(self, event_id: str) -> dict:
        """Inspector: re-deliver a stored event to handlers without a new signature check."""
        return self._stored()[event_id].payload["event"]

    def listing(self) -> list[dict]:
        """Accepted events, newest first, for the inspector."""
        return [
            {
                "event_id": e.payload["event_id"],
                "event_type": e.payload["event_type"],
                "summary": e.payload["event"].get("summary"),
                "lineage_id": e.lineage_id,
                "received_at": e.created_at,
                "seq": e.seq,
            }
            for e in sorted(self._stored().values(), key=lambda e: e.seq, reverse=True)
        ]


def nudge_overdue(gateway: PayPalGateway, ledger: EvidenceLedger, receivables: list[dict], today: date) -> list[dict]:
    """Remind on unpaid invoices past due. One reminder per invoice per day (request id includes the date)."""
    sent = []
    for r in receivables:
        if r["status"] != "PAID" and date.fromisoformat(r["due"]) < today:
            gateway.remind_invoice(r["invoice_id"], request_id(r["lineage_id"], "s7", "remind", r["invoice_id"], today.isoformat()))
            ledger.append(
                r["lineage_id"],
                STAGE,
                "nudge",
                {"invoice_id": r["invoice_id"], "days_overdue": (today - date.fromisoformat(r["due"])).days},
            )
            sent.append(r["invoice_id"])
    return sent
