"""One test per row of the hand-off failure table (docs/ARCHITECTURE.md)."""

import asyncio
from decimal import Decimal

import pytest

from app.core import gates
from app.core.errors import (
    AmountMismatch,
    DoubleCommitment,
    GateTokenInvalid,
    InvoiceNotDraft,
    NotAuthorized,
    NotCaptured,
    SealMissing,
    SealWriteFailed,
    WebhookUnverified,
)
from app.core.lineage import request_id
from app.core.money import LineItem, assert_breakdown_consistent, build_purchase_unit
from app.domain.models import DeliveryReport, Need, Offer, Proposal, VendorInvoice
from app.integrations.paypal import ReplayPayPal
from app.stages import s03_govern, s04_settle, s05_verify, s06_reconcile, s07_payout
from app.stages.s02_negotiate import ReservationBook, SellerAgent, negotiate, schema_gate

SECRET = "test-secret"

LID = "PG-test.0000000001"


def offer(seller="Northwind Displays", price="340", qty=3, ret=30):
    return Offer(seller_id=seller, sku="SKU", turn=3, action="final", unit_price=Decimal(price), quantity=qty, return_days=ret, ship_days=2)


def auto_decision(ledger, mandate, o, lid=LID):
    p = Proposal(
        lineage_id=lid,
        vendor=o.seller_id,
        category="monitors",
        sku=o.sku,
        unit_price=o.unit_price,
        quantity=o.quantity,
        return_days=o.return_days,
        baseline_unit_price=o.unit_price,
    )
    return s03_govern.evaluate(ledger, mandate, p, Decimal("0"))


# 2 -> 3: two sellers both "accept"
def test_only_one_seller_can_be_committed():
    book = ReservationBook("neg-1")
    a, b = book.reserve(offer("Northwind Displays")), book.reserve(offer("Contoso Retail", "350"))
    book.commit(a.reservation_id)
    assert b.status == "CANCELLED"
    with pytest.raises(DoubleCommitment):
        book.commit(b.reservation_id)


def test_schema_gate_drops_bad_json_and_price_walkbacks():
    good = offer().model_dump(mode="json") | {"turn": 2, "action": "counter"}
    assert schema_gate(good, 2, 3, None) is not None
    assert schema_gate(good | {"unit_price": "cheap!"}, 2, 3, None) is None
    assert schema_gate(good | {"note": "extra field"}, 2, 3, None) is None
    assert schema_gate(good, 3, 3, None) is None  # wrong turn
    prev = Offer.model_validate(good | {"unit_price": "300"})
    assert schema_gate(good, 2, 3, prev) is None  # 340 > 300: walked price back up


def test_negotiation_is_bounded_and_commits_exactly_one(mandate):
    sellers = [
        SellerAgent("Northwind Displays", "A", Decimal("389"), Decimal("340")),
        SellerAgent("Contoso Retail", "B", Decimal("412"), Decimal("350")),
    ]
    res = asyncio.run(negotiate("n", mandate, Need(description="m", category="monitors", quantity=3), sellers, Decimal("389")))
    assert max(t["turn"] for t in res.transcript) <= 3
    assert [r.status for r in res.book.reservations.values()].count("COMMITTED") == 1
    assert res.winner.unit_price == Decimal("340")


# 3 -> 4: retry double-charges
def test_retry_with_same_request_id_does_not_double_charge(ledger, mandate):
    gw = ReplayPayPal()
    d = auto_decision(ledger, mandate, offer(qty=1, price="200"))
    first = s04_settle.prepare_order(ledger, gw, SECRET, d, offer(qty=1, price="200"), title="m")
    retry = s04_settle.prepare_order(ledger, gw, SECRET, d, offer(qty=1, price="200"), title="m")
    assert first["order"]["id"] == retry["order"]["id"]
    s04_settle.capture(ledger, gw, LID, first["order"]["id"])
    s04_settle.capture(ledger, gw, LID, first["order"]["id"])
    assert [op for op, _ in gw.calls].count("create_order") == 1
    assert [op for op, _ in gw.calls].count("capture_order") == 1


def test_request_ids_are_deterministic_and_operation_scoped():
    assert request_id(LID, "s4", "capture", "O1") == request_id(LID, "s4", "capture", "O1")
    assert request_id(LID, "s4", "capture", "O1") != request_id(LID, "s4", "capture", "O2")
    assert len(request_id(LID, "s4", "create_order", "x" * 64)) <= 108


def test_human_approval_route_needs_a_valid_approval_token(ledger, mandate, gateway):
    o = offer()  # 1020 > 300 threshold
    d = auto_decision(ledger, mandate, o)
    assert d.route == "HUMAN_APPROVAL"
    with pytest.raises(NotAuthorized):
        s04_settle.prepare_order(ledger, gateway, SECRET, d, o, title="m")
    forged = gates.issue("wrong-secret", gates.APPROVED, LID, d.decision_digest)
    with pytest.raises(NotAuthorized):
        s04_settle.prepare_order(ledger, gateway, SECRET, d, o, title="m", approval_token=forged)
    token = s03_govern.approve(ledger, SECRET, d, "ops")
    assert s04_settle.prepare_order(ledger, gateway, SECRET, d, o, title="m", approval_token=token)["order"]["id"]


def test_tax_rounding_is_penny_exact_and_mismatch_is_caught():
    pu = build_purchase_unit([LineItem("x", "s", Decimal("19.99"), 3, Decimal("0.0825"))], "USD", LID)
    assert pu["amount"]["value"] == "64.92"  # 59.97 + 3 x 1.65
    pu["amount"]["value"] = "64.91"
    with pytest.raises(AmountMismatch):
        assert_breakdown_consistent(pu)


# 4 -> 5: seal missing => no evidence later
def test_seal_write_failure_blocks_capture(ledger, mandate, gateway, monkeypatch):
    o = offer(qty=1, price="200")
    d = auto_decision(ledger, mandate, o)
    real_append = ledger.append
    monkeypatch.setattr(
        ledger,
        "append",
        lambda lid, st, kind, p: (_ for _ in ()).throw(OSError("disk")) if kind == "seal" else real_append(lid, st, kind, p),
    )
    with pytest.raises(SealWriteFailed):
        s04_settle.prepare_order(ledger, gateway, SECRET, d, o, title="m")
    monkeypatch.undo()
    order_id = next(iter(gateway.orders))
    with pytest.raises(SealMissing):
        s04_settle.capture(ledger, gateway, LID, order_id)
    assert not any(op == "capture_order" for op, _ in gateway.calls)


def test_pending_capture_is_not_reported_as_captured(ledger, mandate):
    gw = ReplayPayPal(capture_status="PENDING")
    o = offer(qty=1, price="200")
    prep = s04_settle.prepare_order(ledger, gw, SECRET, auto_decision(ledger, mandate, o), o, title="m")
    with pytest.raises(NotCaptured):
        s04_settle.capture(ledger, gw, LID, prep["order"]["id"])
    assert ledger.latest(LID, "capture") is None


def test_invoice_that_comes_back_live_is_not_sent(ledger):
    gw = ReplayPayPal(invoice_initial_status="SENT")
    with pytest.raises(InvoiceNotDraft):
        s04_settle.issue_invoice(ledger, gw, LID, "a@b.example", [LineItem("x", "s", Decimal("10"), 1)])
    assert not any(op == "send_invoice" for op, _ in gw.calls)


# 5 -> 7 and 6 -> 7: payout before verification / on a flagged invoice
def _settled(ledger, mandate, gateway):
    o = offer(qty=1, price="200")
    prep = s04_settle.prepare_order(ledger, gateway, SECRET, auto_decision(ledger, mandate, o), o, title="m")
    s04_settle.capture(ledger, gateway, LID, prep["order"]["id"])
    return prep["order"]["id"]


def test_payout_requires_verified_and_reconciled_tokens(ledger, mandate, gateway):
    oid = _settled(ledger, mandate, gateway)
    kw = dict(order_id=oid, invoice_number="INV-1", payee_email="p@nw.example", gross=Decimal("200"))
    with pytest.raises(GateTokenInvalid):
        s07_payout.release_payout(ledger, gateway, SECRET, LID, verified_token=None, reconciled_token=None, **kw)
    late = s05_verify.verify_delivery(
        ledger, SECRET, LID, oid, DeliveryReport(tracking_status="DELIVERED", delivered_on="2026-11-12", due_by="2026-11-08")
    )
    assert late["verdict"] == "LATE" and late["token"] is None
    ok = s05_verify.verify_delivery(
        ledger, SECRET, LID, oid, DeliveryReport(tracking_status="DELIVERED", delivered_on="2026-11-07", due_by="2026-11-08")
    )
    recon = s06_reconcile.InvoiceForensics({"Northwind Displays": "p@nw.example"}).check(
        ledger,
        SECRET,
        VendorInvoice(
            vendor="Northwind Displays", invoice_number="INV-1", amount=Decimal("200.00"), payee_email="p@nw.example", lineage_id=LID
        ),
    )
    assert recon["status"] == "CLEAN"
    other = gates.issue(SECRET, gates.VERIFIED, "PG-other.1", oid)  # token from another lineage
    with pytest.raises(GateTokenInvalid):
        s07_payout.release_payout(ledger, gateway, SECRET, LID, verified_token=other, reconciled_token=recon["token"], **kw)
    out = s07_payout.release_payout(ledger, gateway, SECRET, LID, verified_token=ok["token"], reconciled_token=recon["token"], **kw)
    assert out["split"]["net"] == Decimal("195.75")


def test_duplicate_and_spoofed_invoices_are_flagged(ledger, mandate, gateway):
    oid = _settled(ledger, mandate, gateway)
    s05_verify.verify_delivery(
        ledger, SECRET, LID, oid, DeliveryReport(tracking_status="DELIVERED", delivered_on="2026-11-07", due_by="2026-11-08")
    )
    f = s06_reconcile.InvoiceForensics({"Northwind Displays": "p@nw.example"})
    inv = dict(vendor="Northwind Displays", amount=Decimal("200.00"), lineage_id=LID, memo="monitor")
    assert f.check(ledger, SECRET, VendorInvoice(invoice_number="INV-0042", payee_email="p@nw.example", **inv))["status"] == "CLEAN"
    dup = f.check(ledger, SECRET, VendorInvoice(invoice_number="inv 42", payee_email="p@nw.example", **inv))
    assert dup["token"] is None and any(x.startswith("DUPLICATE") for x in dup["flags"])
    spoof = f.check(ledger, SECRET, VendorInvoice(invoice_number="INV-0043", payee_email="pay@nw-billing.example", **inv))
    assert any(x.startswith("PAYEE_MISMATCH") for x in spoof["flags"])
    wrong = f.check(
        ledger, SECRET, VendorInvoice(invoice_number="INV-0044", payee_email="p@nw.example", **(inv | {"amount": Decimal("250")}))
    )
    assert any(x.startswith("AMOUNT_MISMATCH") for x in wrong["flags"])


# 7 -> 8: webhook lost or unverifiable
def test_webhooks_are_verified_deduplicated_and_replayable(ledger):
    inbox = s07_payout.WebhookInbox(ledger, ReplayPayPal())
    evt = {"id": "WH-9", "event_type": "INVOICE.PAID", "resource": {"custom_id": LID}}
    assert inbox.receive({"paypal-transmission-sig": "x"}, evt)["duplicate"] is False
    assert inbox.receive({"paypal-transmission-sig": "x"}, evt)["duplicate"] is True
    assert inbox.replay("WH-9") == evt
    with pytest.raises(WebhookUnverified):
        s07_payout.WebhookInbox(ledger, ReplayPayPal(webhooks_valid=False)).receive({"paypal-transmission-sig": "x"}, evt)
