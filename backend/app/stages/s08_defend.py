"""Stage 8 - DEFEND. The toolkit can only accept_dispute_claim (surrender). We
answer disputes from records sealed *before* the dispute existed: the seal (terms,
price, SKU, return policy, buyer IP), the delivery proof, and the chain of hashes
that shows none of it was edited afterwards.
"""

import io
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from ..core.canonical import sha256_hex
from ..core.errors import DisputeActionUnavailable, DisputeAlreadyAnswered
from ..core.ledger import EvidenceLedger
from ..core.money import q
from ..domain.models import Dispute
from ..integrations.paypal import PayPalGateway

STAGE = "8-defend"

# What each reason needs to be winnable, and which ledger kinds supply it.
REQUIRED = {
    "MERCHANDISE_OR_SERVICE_NOT_RECEIVED": ["seal", "delivery_proof"],
    "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED": ["seal", "delivery_proof", "decision"],
    "UNAUTHORISED": ["seal", "decision", "approval", "delivery_proof"],
    "DUPLICATE_TRANSACTION": ["seal", "capture"],
    "INCORRECT_AMOUNT": ["seal", "capture"],
    "PAYMENT_BY_OTHER_MEANS": ["seal", "capture"],
    "CANCELED_RECURRING_BILLING": ["seal", "capture"],
    "CREDIT_NOT_PROCESSED": ["seal", "capture"],
}


def build_evidence(ledger: EvidenceLedger, dispute: Dispute) -> dict:
    lid = dispute.lineage_id
    found = {kind: ledger.latest(lid, kind) for kind in ("mandate", "decision", "approval", "seal", "delivery_proof", "capture")}
    if found["mandate"] is None:  # mandate lives on the parent lineage
        found["mandate"] = ledger.latest(lid.split(".")[0], "mandate")
    proof = found["delivery_proof"]
    delivered = bool(proof and proof.payload["verdict"] == "PASS")
    needed = REQUIRED.get(dispute.reason, ["seal", "decision"])
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


# ---- live disputes: parse, assess rationally, respond only with a human's go-ahead ------------------
#
# The agent never decides on its own. It gathers facts from the sealed ledger, runs the playbook for the
# dispute's reason, prices each response, applies hard rules, and recommends. A human sends (D-4).

# Economic assumptions behind the expected values. Labelled estimates, not PayPal figures: tune them.
HANDLING_COST = {  # dispute fee exposure + staff time to fight one case, by PayPal lifecycle stage
    "INQUIRY": Decimal("15"),
    "CHARGEBACK": Decimal("20"),
    "PRE_ARBITRATION": Decimal("25"),
    "ARBITRATION": Decimal("25"),
}
RETURN_SHIPPING = Decimal("8")  # prepaid return label for a small item
RECOVERY_RATE = {"defect": Decimal("0.3"), "other": Decimal("0.8")}  # value of the item if it comes back
DEFECT_CAP = 0.35  # a checkout seal proves what was sold, not that this unit still works
ARRIVAL_ODDS = Decimal("0.8")  # an in-transit, not-yet-late parcel that still arrives
DUPLICATE_WINDOW_HOURS = 48

DEFECT_WORDS = (
    "not working",
    "stopped working",
    "stopped",
    "broken",
    "defective",
    "doesn't work",
    "didnt work",
    "didn't work",
    "does not work",
    "faulty",
    "dead",
    "damaged",
)
NOT_RECEIVED_WORDS = ("never arrived", "not received", "didn't arrive", "didnt arrive", "never got", "not delivered")

# PayPal outcome codes -> the WON/LOST label stage 10 learns from.
OUTCOME_LABEL = {
    "RESOLVED_SELLER_FAVOUR": "WON",
    "CANCELED_BY_BUYER": "WON",
    "DENIED": "WON",
    "RESOLVED_BUYER_FAVOUR": "LOST",
    "RESOLVED_WITH_PAYOUT": "LOST",
    "ACCEPTED": "LOST",
    "REFUNDED": "LOST",
}

REFUND_OPTIONS = {"refund_with_return", "partial_refund", "accept"}


@dataclass(frozen=True)
class Playbook:
    label: str
    returnable: bool  # can the buyer physically send goods back?
    evidence_type: str  # provide-evidence evidence_type when contesting
    summary: str


PLAYBOOKS = {
    "MERCHANDISE_OR_SERVICE_NOT_RECEIVED": Playbook(
        "Item not received", False, "PROOF_OF_FULFILLMENT", "Contest only with carrier proof of delivery; inform if still in transit."
    ),
    "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED": Playbook(
        "Not as described", True, "ITEM_DESCRIPTION", "Honour our return window; a defect is a return, not a fight."
    ),
    "UNAUTHORISED": Playbook(
        "Unauthorised payment", False, "OTHER", "Contest only with delivery proof and a human approval on record; flag for security."
    ),
    "DUPLICATE_TRANSACTION": Playbook(
        "Duplicate charge", False, "OTHER", "A second capture for the same vendor and amount is a real duplicate: refund it."
    ),
    "INCORRECT_AMOUNT": Playbook(
        "Incorrect amount", False, "OTHER", "Compare the capture with the sealed price; refund only the difference."
    ),
    "PAYMENT_BY_OTHER_MEANS": Playbook("Paid by other means", False, "OTHER", "One order, one capture on our side is the proof."),
    "CANCELED_RECURRING_BILLING": Playbook(
        "Cancelled recurring billing", False, "OTHER", "We sell one-time orders only; show the single capture."
    ),
    "CREDIT_NOT_PROCESSED": Playbook("Refund not processed", False, "OTHER", "If we already committed to a refund, honour it."),
}

STATE_NOTE = {
    "WAITING_FOR_BUYER_RESPONSE": "Waiting on the buyer: our last response is with them.",
    "UNDER_REVIEW": "PayPal is reviewing the case. Nothing to send until it asks.",
    "RESOLVED": "Resolved.",
    "OPEN": "Open, but PayPal isn't asking us for anything yet.",
}


@dataclass
class DisputeCase:
    dispute_id: str
    reason: str
    stage: str
    status: str
    amount: Decimal
    currency: str
    lineage_id: str | None
    capture_id: str | None
    item_name: str
    buyer_note: str
    due_date: str | None
    created: str | None
    updated: str | None = None
    actions: list[str] = field(default_factory=list)
    allowed_offer_types: list[str] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    outcome: str | None = None

    def as_dispute(self, lineage_id: str | None = None) -> Dispute:
        return Dispute(
            dispute_id=self.dispute_id,
            lineage_id=lineage_id or self.lineage_id or f"DISPUTE-{self.dispute_id}",
            reason=self.reason,
            amount=self.amount,
            seller_response_due_date=(self.due_date or "")[:10],
        )


def parse_paypal_dispute(raw: dict) -> DisputeCase:
    """GET /v1/customer/disputes/{id} -> DisputeCase. The lineage rides in disputed_transactions[].custom
    because Orders custom_id carries it (core/money.build_purchase_unit)."""
    tx = (raw.get("disputed_transactions") or [{}])[0]
    amt = raw.get("dispute_amount") or {}
    offer_opts = raw.get("allowed_response_options", {}).get("make_offer", {}).get("offer_types", [])
    if not offer_opts:
        # PayPal omits allowed_response_options on some cases; it rejects a return on goods never received.
        offer_opts = ["REFUND"] if raw.get("reason") == "MERCHANDISE_OR_SERVICE_NOT_RECEIVED" else ["REFUND", "REFUND_WITH_RETURN"]
    return DisputeCase(
        dispute_id=raw["dispute_id"],
        reason=raw.get("reason", "OTHER"),
        stage=raw.get("dispute_life_cycle_stage", ""),
        status=raw.get("status", ""),
        amount=Decimal(str(amt.get("value", "0"))),
        currency=amt.get("currency_code", "USD"),
        lineage_id=tx.get("custom") or None,
        capture_id=tx.get("seller_transaction_id"),
        item_name=tx.get("item_name", ""),
        buyer_note=tx.get("notes") or raw.get("buyer_note") or "",
        due_date=raw.get("seller_response_due_date"),
        created=raw.get("create_time"),
        updated=raw.get("update_time"),
        # HATEOAS: only what PayPal lists in links is allowed right now.
        actions=sorted({link["rel"] for link in raw.get("links", []) if link.get("method", "POST") == "POST"}),
        allowed_offer_types=offer_opts,
        messages=[
            {"posted_by": m.get("posted_by", ""), "time_posted": m.get("time_posted"), "content": m.get("content", "")}
            for m in raw.get("messages", [])
        ],
        outcome=(raw.get("dispute_outcome") or {}).get("outcome_code"),
    )


def locate(case: DisputeCase, ledgers: list[EvidenceLedger]) -> tuple[EvidenceLedger | None, str | None]:
    """Find the sealed record: by the lineage PayPal echoed back, else by matching the capture ID."""
    for led in ledgers:
        if case.lineage_id and led.latest(case.lineage_id, "seal"):
            return led, case.lineage_id
    if case.capture_id:
        for led in ledgers:
            for e in led.entries(kind="capture"):
                if e.payload.get("capture_id") == case.capture_id:
                    return led, e.lineage_id
    return None, case.lineage_id


def classify_note(note: str) -> str:
    n = note.lower()
    if any(w in n for w in NOT_RECEIVED_WORDS):
        return "not_received"
    if any(w in n for w in DEFECT_WORDS):
        return "defect"
    return "other"


def _ledger_facts(ledger: EvidenceLedger, lineage_id: str, dispute_id: str, today: date) -> dict:
    """Everything the playbooks need, read from the sealed record."""
    seal = ledger.latest(lineage_id, "seal")
    decision = ledger.latest(lineage_id, "decision")
    captures = ledger.entries(lineage_id, "capture")
    proof = ledger.latest(lineage_id, "delivery_proof")
    # The decision holds the true return window: None when the merchant hid it (the seal's offer says 0).
    rd = decision.payload["proposal"]["return_days"] if decision else seal.payload.get("return_days")
    bought = datetime.fromisoformat(seal.created_at).date()
    captured = Decimal(captures[-1].payload["amount"]["value"]) if captures else None

    # Duplicate check across the whole mandate: another capture, same vendor and amount, close in time.
    mandate_lid = lineage_id.split(".")[0]
    t0 = datetime.fromisoformat(captures[-1].created_at) if captures else None
    duplicates = []
    if captures:
        for c in ledger.entries(mandate_lid, "capture"):
            if c.lineage_id == lineage_id:
                continue
            other_seal = ledger.latest(c.lineage_id, "seal")
            same = (
                other_seal
                and other_seal.payload.get("seller_id") == seal.payload.get("seller_id")
                and Decimal(c.payload["amount"]["value"]) == captured
            )
            if same and abs((datetime.fromisoformat(c.created_at) - t0).total_seconds()) <= DUPLICATE_WINDOW_HOURS * 3600:
                duplicates.append({"lineage_id": c.lineage_id, "capture_id": c.payload.get("capture_id"), "at": c.created_at})

    responses = ledger.entries(lineage_id, "dispute_response")
    commitment = next((e for e in responses if e.payload.get("option") in REFUND_OPTIONS), None)
    return {
        "order_id": seal.payload["order_id"],
        "seller_id": seal.payload.get("seller_id"),
        "purchased_on": bought.isoformat(),
        "sealed_at": seal.created_at,
        "days_since_purchase": (today - bought).days,
        "sealed_return_days": rd,
        "within_return_window": rd is not None and (today - bought).days <= rd,
        "terms_hash": seal.payload["terms_hash"],
        "sealed_amount": seal.payload.get("amount"),
        "captured_amount": format(captured, "f") if captured is not None else None,
        "captures_on_order": len(captures),
        "duplicate_captures": duplicates,
        "human_approved": bool(ledger.latest(lineage_id, "approval")),
        "delivery_status": proof.payload.get("tracking_status") if proof else None,
        "delivery_verdict": proof.payload.get("verdict") if proof else None,
        "delivery_due_by": proof.payload.get("due_by") if proof else None,
        "tracking": {"carrier": proof.payload.get("carrier"), "number": proof.payload.get("tracking_number")} if proof else None,
        "delivered": bool(proof and proof.payload.get("tracking_status") == "DELIVERED"),
        "refund_committed_at": commitment.created_at if commitment else None,
        "refund_committed_by": commitment.payload.get("option") if commitment else None,
        "earlier_disputes": sorted({e.payload["dispute_id"] for e in responses if e.payload["dispute_id"] != dispute_id}),
        "responses": [
            {"option": e.payload.get("option"), "via": e.payload.get("via"), "at": e.created_at, "approver": e.payload.get("approver")}
            for e in responses
            if e.payload["dispute_id"] == dispute_id
        ],
    }


def _via(case: DisputeCase, prefs: list[str]) -> str:
    """First channel PayPal allows right now, else the preferred one (shown as unavailable)."""
    return next((v for v in prefs if v in case.actions), prefs[0])


def assess(
    case: DisputeCase, ledger: EvidenceLedger | None, lineage_id: str | None, today: date, *, return_address_set: bool = True
) -> dict:
    """Deterministic: facts from the sealed record, the reason's playbook, expected value per option,
    hard policy rules, and only the channels PayPal currently allows. The LLM never decides."""
    found = bool(ledger and lineage_id and ledger.latest(lineage_id, "seal"))
    bundle = build_evidence(ledger, case.as_dispute(lineage_id)) if found else None
    book = PLAYBOOKS.get(case.reason)
    facts: dict = {"lineage_found": found, "claim": classify_note(case.buyer_note), "playbook": book.label if book else None}
    if found:
        facts |= _ledger_facts(ledger, lineage_id, case.dispute_id, today)
        facts |= {"chain_ok": bundle["chain_ok"], "missing_evidence": bundle["missing"]}
    flags: list[str] = []
    A = case.amount
    H = HANDLING_COST.get(case.stage, HANDLING_COST["INQUIRY"])
    p = bundle["win_odds"] if bundle else 0.05

    # ---- reason playbooks: adjust odds, add reason-specific options and exclusions ----
    excl: dict[str, str] = {}
    extra: list[dict] = []
    reason = case.reason
    if facts["claim"] == "defect":
        p = min(p, DEFECT_CAP)
    if found and reason == "MERCHANDISE_OR_SERVICE_NOT_RECEIVED":
        if facts["delivered"]:
            p = max(p, 0.85)  # carrier confirmed delivery: the classic winnable INR
        else:
            p = min(p, 0.15)
            due_by = facts.get("delivery_due_by")
            if facts["delivery_status"] == "IN_TRANSIT" and due_by and date.fromisoformat(due_by) >= today:
                extra.append(
                    {
                        "option": "inform",
                        "via": _via(case, ["send_message"]),
                        "ev": q(ARRIVAL_ODDS * A),
                        "basis": f"parcel in transit, due {due_by}: ~{ARRIVAL_ODDS:.0%} it arrives and the case closes",
                    }
                )
                excl["accept"] = f"The parcel is in transit and not late (due {due_by}): tell the buyer before refunding."
    elif found and reason == "UNAUTHORISED":
        flags.append("Possible compromised buyer account: review before any response.")
        if not (facts["delivered"] and facts["human_approved"]):
            p = min(p, 0.15)
    elif found and reason == "DUPLICATE_TRANSACTION":
        if facts["duplicate_captures"]:
            excl["contest"] = "A second capture for the same vendor and amount exists: this is a real duplicate."
            flags.append(f"Duplicate capture found: {facts['duplicate_captures'][0]['capture_id']}.")
        elif facts["captures_on_order"] == 1:
            p = max(p, 0.9)  # deterministic PayPal-Request-Id: one order, one capture
    elif found and reason == "INCORRECT_AMOUNT":
        sealed, captured = Decimal(facts["sealed_amount"]), Decimal(facts["captured_amount"] or "0")
        if captured > sealed:
            diff = q(captured - sealed)
            excl["contest"] = f"We captured {captured} against a sealed price of {sealed}: the buyer is right."
            extra.append(
                {
                    "option": "partial_refund",
                    "via": _via(case, ["make_offer", "send_message"]),
                    "ev": q(max(A - diff, Decimal("0"))),
                    "basis": f"refund the {diff} overcharge, keep the rest of the {A} disputed",
                    "amount": format(diff, "f"),
                }
            )
        else:
            p = max(p, 0.85)  # the penny-exact seal proves the agreed amount
    elif found and reason in ("PAYMENT_BY_OTHER_MEANS", "CANCELED_RECURRING_BILLING"):
        if facts["captures_on_order"] == 1 and not facts["duplicate_captures"]:
            p = max(p, 0.8)
        else:
            excl["contest"] = "More than one capture is on record for this purchase."
    elif found and reason == "CREDIT_NOT_PROCESSED":
        if facts["refund_committed_at"]:
            excl["contest"] = f"We committed to a refund ({facts['refund_committed_by']}) on {facts['refund_committed_at'][:10]}."
        else:
            p = min(p, 0.5)
    if not book:
        flags.append(f"No playbook for {reason}: review manually.")
    if found and facts["earlier_disputes"]:
        flags.append(f"This purchase was disputed before: {', '.join(facts['earlier_disputes'])}.")
    if found and facts.get("captured_amount") and A > Decimal(facts["captured_amount"]):
        flags.append(f"Disputed {A} is more than the {facts['captured_amount']} captured.")

    # ---- options (most to least adversarial) ----
    rec = RECOVERY_RATE["defect" if facts["claim"] == "defect" else "other"]
    options = [
        {
            "option": "contest",
            "via": _via(case, ["provide_evidence", "send_message"]),
            "ev": q(Decimal(str(p)) * A - H),
            "basis": f"{p:.0%} x {A} kept, minus {H} handling at {case.stage or 'INQUIRY'}",
        },
        *[o for o in extra if o["option"] == "inform"],
        *[o for o in extra if o["option"] == "partial_refund"],
    ]
    if book is None or book.returnable:
        options.append(
            {
                "option": "refund_with_return",
                "via": _via(case, ["make_offer", "send_message"]),
                "ev": q(rec * A - RETURN_SHIPPING),
                "basis": f"refund {A}, item back worth ~{rec:.0%} ({facts['claim']}), minus {RETURN_SHIPPING} return label",
            }
        )
    options.append(
        {
            "option": "accept",
            "via": _via(case, ["accept_claim", "make_offer", "send_message"]),
            "ev": Decimal("0.00"),
            "basis": f"refund the {A} disputed, close the case",
        }
    )

    # ---- hard rules ----
    if not found:
        excl.setdefault("contest", "No sealed record for this payment: we won't contest without evidence.")
    elif facts.get("within_return_window") and reason == "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED":
        excl.setdefault("contest", f"Inside the sealed {facts['sealed_return_days']}-day return window: honour our own terms.")
    elif reason == "MERCHANDISE_OR_SERVICE_NOT_RECEIVED" and not facts["delivered"]:
        excl.setdefault("contest", "No carrier proof of delivery: record tracking (stage 5) before contesting.")
    for o in options:
        o["available"] = o["via"] in case.actions
        o["excluded_by"] = excl.get(o["option"])
        if o["option"] == "refund_with_return" and not o["excluded_by"]:
            if o["via"] == "make_offer" and "REFUND_WITH_RETURN" not in case.allowed_offer_types:
                o["excluded_by"] = "PayPal doesn't allow a refund-with-return offer on this case."
            elif o["via"] == "make_offer" and not return_address_set:
                o["excluded_by"] = "No returns address configured (RETURN_ADDRESS_* in .env)."
    due = date.fromisoformat(case.due_date[:10]) if case.due_date else None
    days_left = (due - today).days if due else None
    if days_left is not None and days_left < 0:
        for o in options:
            o["excluded_by"] = o["excluded_by"] or "Seller response window has closed."

    # ---- recommendation: only when PayPal is waiting on us and a playbook applies ----
    state_note = None if case.status == "WAITING_FOR_SELLER_RESPONSE" else STATE_NOTE.get(case.status, f"Status {case.status}.")
    if case.status == "RESOLVED" and case.outcome:
        state_note = f"Resolved: {case.outcome.replace('_', ' ').lower()} ({OUTCOME_LABEL.get(case.outcome, 'unlabelled')})."
    eligible = [o for o in options if o["available"] and not o["excluded_by"]]
    best = max(eligible, key=lambda o: (o["ev"], options.index(o))) if eligible else None
    recommended = best["option"] if best and not state_note and book else None
    return {
        "dispute_id": case.dispute_id,
        "lineage_id": lineage_id,
        "reason_label": book.label if book else reason,
        "playbook": book.summary if book else None,
        "win_odds": round(p, 2),
        "days_left": days_left,
        "state_note": state_note,
        "flags": flags,
        "facts": facts,
        "options": options,
        "recommended": recommended,
        "assumptions": {
            "handling_cost": H,
            "return_shipping": RETURN_SHIPPING,
            "recovery_rate": RECOVERY_RATE,
            "defect_cap": DEFECT_CAP,
            "arrival_odds": ARRIVAL_ODDS,
        },
    }


def draft_reply(case: DisputeCase, assessment: dict, option: str) -> str:
    """Template reply built only from sealed facts. Shown to a human, who can edit it before sending."""
    f = assessment["facts"]
    item = case.item_name or "item"
    sealed = (
        f"Our records for order {f['order_id']} were sealed at checkout on {f['purchased_on']} (terms fingerprint {f['terms_hash'][:12]}…)"
        if f["lineage_found"]
        else "We could not match this payment to a sealed order record"
    )
    opt = next((o for o in assessment["options"] if o["option"] == option), {})
    if option == "inform":
        t = f.get("tracking") or {}
        return (
            f"Hello, thanks for reaching out. {sealed}. Your {item} is on its way with {t.get('carrier')} "
            f"(tracking {t.get('number')}), due by {f.get('delivery_due_by')}. "
            "If it hasn't arrived by then, reply here and we'll refund you."
        )
    if option == "partial_refund":
        return (
            f"Hello, you're right, and we're sorry. {sealed}: the agreed price was {f.get('sealed_amount')} {case.currency}, "
            f"and we charged {f.get('captured_amount')}. We're refunding the {opt.get('amount')} difference."
        )
    if option == "contest":
        why = {
            "MERCHANDISE_OR_SERVICE_NOT_RECEIVED": (
                f"The carrier confirms delivery ({(f.get('tracking') or {}).get('carrier')} {(f.get('tracking') or {}).get('number')})"
            ),
            "DUPLICATE_TRANSACTION": "Our records show exactly one order and one payment for this purchase",
            "INCORRECT_AMOUNT": f"The amount charged matches the price agreed at checkout ({f.get('sealed_amount')} {case.currency})",
            "PAYMENT_BY_OTHER_MEANS": "Our records show this purchase was paid once, through this PayPal payment",
            "CANCELED_RECURRING_BILLING": "This was a one-time purchase, not a subscription",
        }.get(case.reason, "The item was sold as listed")
        return (
            f"Hello, thank you for raising this. {sealed}. {why}"
            + (", and the purchase was reviewed and approved before payment" if f.get("human_approved") else "")
            + ". We have attached the sealed record. If something is still wrong, we're glad to help."
        )
    if option == "refund_with_return":
        trouble = "stopped working" if f["claim"] == "defect" else "isn't what you expected"
        return (
            f"Hello, we're sorry the {item} {trouble}. {sealed}. "
            f"We'll refund {case.amount} {case.currency} once the item is returned; we'll send a prepaid return label."
        )
    return f"Hello, we're sorry for the trouble. {sealed}. We are refunding {case.amount} {case.currency} in full."


def offer_body(case: DisputeCase, amount: Decimal, note: str, return_address: dict | None = None) -> dict:
    """POST /make-offer body. With a return address it's REFUND_WITH_RETURN; without, a money-only REFUND,
    which is also how a partial refund (amount below the disputed amount) goes out."""
    body = {
        "note": note[:2000],
        "offer_amount": {"currency_code": case.currency, "value": format(q(amount), "f")},
        "offer_type": "REFUND_WITH_RETURN" if return_address else "REFUND",
    }
    if return_address:
        body["return_shipping_address"] = return_address
    return body


def respond(
    gateway: PayPalGateway,
    ledger: EvidenceLedger,
    case: DisputeCase,
    assessment: dict,
    *,
    option: str,
    note: str,
    approver: str,
    return_address: dict | None = None,
) -> dict:
    """Send the chosen response. Called only from a human's explicit approval (D-4). The option must be
    one PayPal allows right now, and each response is sent once."""
    chosen = next((o for o in assessment["options"] if o["option"] == option), None)
    if chosen is None or not chosen["available"]:
        raise DisputeActionUnavailable(
            f"{option} is not allowed for this dispute right now", dispute_id=case.dispute_id, allowed=case.actions
        )
    if chosen["excluded_by"]:
        raise DisputeActionUnavailable(chosen["excluded_by"], dispute_id=case.dispute_id)
    can_return = option == "refund_with_return" and "REFUND_WITH_RETURN" in case.allowed_offer_types
    if chosen["via"] == "make_offer" and can_return and not return_address:
        # PayPal rejects REFUND_WITH_RETURN without one (MISSING_RETURN_SHIPPING_ADDRESS); refuse before calling.
        raise DisputeActionUnavailable("set RETURN_ADDRESS_* in .env before offering a refund on return", dispute_id=case.dispute_id)
    lid = assessment["lineage_id"] or f"DISPUTE-{case.dispute_id}"
    if any(
        e.payload["dispute_id"] == case.dispute_id and e.payload.get("option") == option for e in ledger.entries(lid, "dispute_response")
    ):
        raise DisputeAlreadyAnswered(f"{option} already sent for {case.dispute_id}", dispute_id=case.dispute_id)

    amount = Decimal(chosen.get("amount", case.amount))
    book = PLAYBOOKS.get(case.reason)
    if chosen["via"] == "provide_evidence":
        d = case.as_dispute(lid)
        bundle = build_evidence(ledger, d)
        ev = bundle["paypal_evidence"]["evidences"][0]
        ev["notes"] = note[:2000]
        if book and not (book.evidence_type == "PROOF_OF_FULFILLMENT" and not assessment["facts"].get("delivered")):
            ev["evidence_type"] = book.evidence_type
        resp = gateway.provide_evidence(
            case.dispute_id, bundle["paypal_evidence"], [(f"{case.dispute_id}-brief.pdf", render_pdf(d, bundle))]
        )
    elif chosen["via"] == "send_message":
        resp = gateway.dispute_action(case.dispute_id, "send_message", {"message": note[:2000]})
    elif chosen["via"] == "make_offer":
        resp = gateway.dispute_action(case.dispute_id, "make_offer", offer_body(case, amount, note, return_address if can_return else None))
    else:
        resp = gateway.dispute_action(case.dispute_id, "accept_claim", {"note": note[:2000]})

    ledger.append(
        lid,
        STAGE,
        "dispute_response",
        {
            "dispute_id": case.dispute_id,
            "reason": case.reason,
            "option": option,
            "via": chosen["via"],
            "amount": format(q(amount), "f"),
            "win_odds": assessment["win_odds"],
            "ev": str(chosen["ev"]),
            "recommended": assessment["recommended"],
            "followed_recommendation": option == assessment["recommended"],
            "approver": approver,
            "note_hash": sha256_hex(note),
            "missing": assessment["facts"].get("missing_evidence", []),
        },
    )
    return resp


def sync_outcome(ledger: EvidenceLedger, case: DisputeCase, lineage_id: str) -> str | None:
    """When PayPal resolves a case, label it WON/LOST once so stage 10 can learn from it."""
    label = OUTCOME_LABEL.get(case.outcome or "")
    if case.status != "RESOLVED" or not label:
        return None
    if any(e.payload["dispute_id"] == case.dispute_id for e in ledger.entries(lineage_id, "dispute_outcome")):
        return label
    seal = ledger.latest(lineage_id, "seal")
    record_outcome(ledger, case.as_dispute(lineage_id), label, seal.payload.get("seller_id", "") if seal else "")
    return label


def timeline(case: DisputeCase, assessment: dict) -> list[dict]:
    """Every dated moment of a case, oldest first: our sealed purchase, the dispute, messages, our responses."""
    f = assessment["facts"]
    out = []
    if f.get("sealed_at"):
        out.append({"at": f["sealed_at"], "who": "ledger", "what": f"Purchase sealed (order {f['order_id']})"})
    if case.created:
        out.append(
            {"at": case.created, "who": "buyer", "what": f"Dispute opened: {assessment['reason_label']}, {case.amount} {case.currency}"}
        )
    for m in case.messages:
        if m.get("time_posted"):
            out.append({"at": m["time_posted"], "who": m["posted_by"].lower() or "paypal", "what": f"Message: {m['content'][:140]}"})
    for r in f.get("responses", []):
        out.append(
            {"at": r["at"], "who": "us", "what": f"Sent {r['option'].replace('_', ' ')} via {r['via'].replace('_', ' ')} ({r['approver']})"}
        )
    if case.updated and case.status == "RESOLVED":
        out.append({"at": case.updated, "who": "paypal", "what": assessment["state_note"] or "Resolved"})
    out.sort(key=lambda e: _as_utc(e["at"]))
    if case.due_date and case.status == "WAITING_FOR_SELLER_RESPONSE":
        out.append({"at": case.due_date, "who": "deadline", "what": f"Respond by ({assessment['days_left']} days left)"})
    return out


def _as_utc(ts: str) -> datetime:
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=UTC)
