"""Stage 4 - SETTLE and SEAL.

Order of operations is the guard:
  1. pre-flight: penny-exact breakdown (AMOUNT_MISMATCH can't reach PayPal)
  2. authorization: AUTO_SETTLE decision, or an APPROVED gate token for this decision
  3. create order with a digest-derived PayPal-Request-Id (retries can't double-create)
  4. write the Decide-and-Prove seal; if that write fails, stop - nothing is captured
  5. capture only if a seal for this order exists; trust only captures[].status
"""

from decimal import Decimal

from ..core.canonical import sha256_hex
from ..core.errors import AmountMismatch, InvoiceNotDraft, NotAuthorized, NotCaptured, SealMissing, SealWriteFailed
from ..core.gates import APPROVED, require
from ..core.ledger import EvidenceLedger
from ..core.lineage import request_id
from ..core.money import LineItem, build_purchase_unit, q
from ..domain.models import Decision, Offer
from ..integrations.paypal import PayPalGateway

STAGE = "4-settle"


def prepare_order(
    ledger: EvidenceLedger,
    gateway: PayPalGateway,
    secret: str,
    decision: Decision,
    offer: Offer,
    *,
    title: str,
    tax_rate: Decimal = Decimal("0"),
    approval_token: str | None = None,
    buyer_ip: str = "0.0.0.0",
    currency: str = "USD",
) -> dict:
    lid = decision.lineage_id
    if decision.route == "BLOCKED":
        raise NotAuthorized("firewall blocked this transaction", lineage_id=lid)
    if decision.route == "HUMAN_APPROVAL":
        try:
            require(secret, approval_token, APPROVED, lid, decision.decision_digest)
        except Exception as e:
            raise NotAuthorized("human approval required", lineage_id=lid) from e

    pu = build_purchase_unit([LineItem(title, offer.sku, offer.unit_price, offer.quantity, tax_rate)], currency, lid, description=title)
    order = gateway.create_order(pu, request_id(lid, "s4", "create_order", decision.decision_digest))

    seal = {
        "order_id": order["id"],
        "decision_digest": decision.decision_digest,
        "seller_id": offer.seller_id,
        "sku": offer.sku,
        "unit_price": str(offer.unit_price),
        "quantity": offer.quantity,
        "amount": pu["amount"]["value"],
        "currency": currency,
        "return_days": offer.return_days,
        "ship_days": offer.ship_days,
        "terms_hash": sha256_hex(offer.terms),
        "terms_text": offer.terms,
        "buyer_ip": buyer_ip,
    }
    try:
        ledger.append(lid, STAGE, "seal", seal)
    except Exception as e:
        raise SealWriteFailed("seal write failed; order left uncaptured", order_id=order["id"]) from e
    return {"order": order, "purchase_unit": pu, "seal": seal}


def capture(ledger: EvidenceLedger, gateway: PayPalGateway, lineage_id: str, order_id: str) -> dict:
    seals = [e for e in ledger.entries(lineage_id, "seal") if e.payload["order_id"] == order_id]
    if not seals:
        raise SealMissing("no seal for order; refusing to capture", order_id=order_id)
    resp = gateway.capture_order(order_id, request_id(lineage_id, "s4", "capture", order_id))
    caps = [c for pu in resp.get("purchase_units", []) for c in pu.get("payments", {}).get("captures", [])]
    # Guard against false 'captured': order status COMPLETED doesn't mean the money moved.
    if not caps or caps[0]["status"] != "COMPLETED":
        status = caps[0]["status"] if caps else "NO_CAPTURE"
        ledger.append(lineage_id, STAGE, "capture_failed", {"order_id": order_id, "capture_status": status})
        raise NotCaptured(f"capture status {status}", order_id=order_id)
    ledger.append(lineage_id, STAGE, "capture", {"order_id": order_id, "capture_id": caps[0]["id"], "amount": caps[0]["amount"]})
    return caps[0]


def issue_invoice(
    ledger: EvidenceLedger, gateway: PayPalGateway, lineage_id: str, recipient_email: str, items: list[LineItem], currency="USD"
) -> dict:
    """Draft-first invoicing: create, confirm it's a DRAFT with the expected total, then send."""
    expected = sum((q(i.unit_amount) * i.quantity + i.unit_tax * i.quantity for i in items), Decimal("0"))
    body = {
        "detail": {"currency_code": currency, "reference": lineage_id, "note": f"Lineage {lineage_id}"},
        "primary_recipients": [{"billing_info": {"email_address": recipient_email}}],
        "items": [
            {
                "name": i.name,
                "quantity": str(i.quantity),
                "unit_amount": {"currency_code": currency, "value": format(q(i.unit_amount), "f")},
                "tax": {"name": "Tax", "percent": format(i.tax_rate * 100, "f")},
            }
            for i in items
        ],
    }
    inv = gateway.create_invoice(body, request_id(lineage_id, "s4", "create_invoice"))
    if inv.get("status") != "DRAFT":
        raise InvoiceNotDraft(f"invoice came back {inv.get('status')}; not sending", invoice_id=inv.get("id"))
    got = inv.get("amount", {}).get("value")
    if got is not None and Decimal(got) != expected:
        raise AmountMismatch(f"invoice total {got} != expected {expected}", invoice_id=inv["id"])
    sent = gateway.send_invoice(inv["id"], request_id(lineage_id, "s4", "send_invoice", inv["id"]))
    ledger.append(lineage_id, STAGE, "invoice", {"invoice_id": inv["id"], "expected_total": str(expected), "status": "SENT"})
    return sent
