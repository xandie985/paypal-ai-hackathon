"""Stage 8 - DEFEND. The toolkit can only accept_dispute_claim (surrender). We
answer disputes from records sealed *before* the dispute existed: the seal (terms,
price, SKU, return policy, buyer IP), the delivery proof, and the chain of hashes
that shows none of it was edited afterwards.
"""

import io
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
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
    "UNAUTHORISED": ["seal", "decision", "approval"],
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

# Economic assumptions behind the expected values. Labelled estimates, not PayPal figures: tune them.
HANDLING_COST = Decimal("15")  # staff time + dispute fee exposure to fight one case
RETURN_SHIPPING = Decimal("8")  # prepaid return label for a small item
RECOVERY_RATE = {"defect": Decimal("0.3"), "other": Decimal("0.8")}  # value of the item if it comes back
DEFECT_CAP = 0.35  # a checkout seal proves what was sold, not that this unit still works

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
    actions: list[str] = field(default_factory=list)

    def as_dispute(self) -> Dispute:
        return Dispute(
            dispute_id=self.dispute_id,
            lineage_id=self.lineage_id or f"DISPUTE-{self.dispute_id}",
            reason=self.reason,
            amount=self.amount,
            seller_response_due_date=(self.due_date or "")[:10],
        )


def parse_paypal_dispute(raw: dict) -> DisputeCase:
    """GET /v1/customer/disputes/{id} -> DisputeCase. The lineage rides in disputed_transactions[].custom
    because Orders custom_id carries it (core/money.build_purchase_unit)."""
    tx = (raw.get("disputed_transactions") or [{}])[0]
    amt = raw.get("dispute_amount") or {}
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
        # HATEOAS: only what PayPal lists in links is allowed right now.
        actions=sorted({link["rel"] for link in raw.get("links", []) if link.get("method", "POST") == "POST"}),
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


def assess(
    case: DisputeCase, ledger: EvidenceLedger | None, lineage_id: str | None, today: date, *, return_address_set: bool = True
) -> dict:
    """Deterministic: facts from the sealed record, expected value per option, hard policy rules,
    and only the options PayPal currently allows. The LLM never decides; at most it rewords the draft."""
    found = bool(ledger and lineage_id and ledger.latest(lineage_id, "seal"))
    case_for_bundle = DisputeCase(**{**asdict(case), "lineage_id": lineage_id})
    bundle = build_evidence(ledger, case_for_bundle.as_dispute()) if found else None
    facts: dict = {"lineage_found": found, "claim": classify_note(case.buyer_note)}
    if found:
        seal = ledger.latest(lineage_id, "seal")
        decision = ledger.latest(lineage_id, "decision")
        # The decision holds the true return window: None when the merchant hid it (the seal's offer says 0).
        rd = decision.payload["proposal"]["return_days"] if decision else seal.payload.get("return_days")
        bought = datetime.fromisoformat(seal.created_at).date()
        facts |= {
            "order_id": seal.payload["order_id"],
            "purchased_on": bought.isoformat(),
            "days_since_purchase": (today - bought).days,
            "sealed_return_days": rd,
            "within_return_window": rd is not None and (today - bought).days <= rd,
            "terms_hash": seal.payload["terms_hash"],
            "human_approved": bool(ledger.latest(lineage_id, "approval")),
            "delivered": bool(bundle["records"].get("delivery_proof") and bundle["records"]["delivery_proof"].get("verdict") == "PASS"),
            "chain_ok": bundle["chain_ok"],
            "missing_evidence": bundle["missing"],
        }

    p_win = bundle["win_odds"] if bundle else 0.05
    if facts["claim"] == "defect":
        p_win = min(p_win, DEFECT_CAP)
    A = case.amount
    rec = RECOVERY_RATE["defect" if facts["claim"] == "defect" else "other"]
    options = [
        {
            "option": "contest",
            "via": "provide_evidence" if "provide_evidence" in case.actions else "send_message",
            "ev": q(Decimal(str(p_win)) * A - HANDLING_COST),
            "basis": f"{p_win:.0%} x {A} kept, minus {HANDLING_COST} handling",
        },
        {
            "option": "refund_with_return",
            "via": "make_offer",
            "ev": q(rec * A - RETURN_SHIPPING),
            "basis": f"refund {A}, item back worth ~{rec:.0%} ({facts['claim']}), minus {RETURN_SHIPPING} return label",
        },
        {"option": "accept", "via": "accept_claim", "ev": Decimal("0.00"), "basis": "refund the disputed amount, close the case"},
    ]
    due = date.fromisoformat(case.due_date[:10]) if case.due_date else None
    days_left = (due - today).days if due else None
    for o in options:
        # In an INQUIRY PayPal may list only send_message; a refund or acceptance can still be proposed in a message.
        if o["via"] not in case.actions and o["option"] != "contest" and "send_message" in case.actions:
            o["via"] = "send_message"
        o["available"] = o["via"] in case.actions
        o["excluded_by"] = None
    contest = options[0]
    if not found:
        contest["excluded_by"] = "No sealed record for this payment: we won't contest without evidence."
    elif facts.get("within_return_window") and case.reason == "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED":
        contest["excluded_by"] = f"Inside the sealed {facts['sealed_return_days']}-day return window: honour our own terms."
    if options[1]["via"] == "make_offer" and not return_address_set:
        options[1]["excluded_by"] = "No returns address configured (RETURN_ADDRESS_* in .env)."
    if days_left is not None and days_left < 0:
        for o in options:
            o["excluded_by"] = o["excluded_by"] or "Seller response window has closed."

    eligible = [o for o in options if o["available"] and not o["excluded_by"]]
    # Highest EV wins; on a tie prefer the less adversarial option (list order is most to least adversarial).
    best = max(eligible, key=lambda o: (o["ev"], options.index(o))) if eligible else None
    return {
        "dispute_id": case.dispute_id,
        "lineage_id": lineage_id,
        "win_odds": round(p_win, 2),
        "days_left": days_left,
        "facts": facts,
        "options": options,
        "recommended": best["option"] if best else None,
        "assumptions": {
            "handling_cost": HANDLING_COST,
            "return_shipping": RETURN_SHIPPING,
            "recovery_rate": RECOVERY_RATE,
            "defect_cap": DEFECT_CAP,
        },
    }


def draft_reply(case: DisputeCase, assessment: dict, option: str) -> str:
    """Template reply built only from sealed facts. Shown to a human, who can edit it before sending."""
    f = assessment["facts"]
    sealed = (
        (
            f"Our records for order {f['order_id']} were sealed at checkout on {f['purchased_on']} "
            f"(terms fingerprint {f['terms_hash'][:12]}…)"
        )
        if f["lineage_found"]
        else "We could not match this payment to a sealed order record"
    )
    if option == "contest":
        return (
            f"Hello, thank you for raising this. {sealed}. The item was sold as listed"
            + (", and the purchase was reviewed and approved before payment" if f.get("human_approved") else "")
            + ". We have attached the sealed record. If something is wrong with the unit, we are glad to help with a"
            " repair or warranty claim."
        )

    if option == "refund_with_return":
        return (
            f"Hello, we're sorry the {case.item_name or 'item'} stopped working for you. {sealed}. "
            f"We'll refund {case.amount} {case.currency} once the item is returned; we'll send a prepaid return label."
        )
    return f"Hello, we're sorry for the trouble. {sealed}. We are refunding {case.amount} {case.currency} in full."


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
    if chosen["via"] == "make_offer" and not return_address:
        # PayPal rejects REFUND_WITH_RETURN without one (MISSING_RETURN_SHIPPING_ADDRESS); refuse before calling.
        raise DisputeActionUnavailable("set RETURN_ADDRESS_* in .env before offering a refund on return", dispute_id=case.dispute_id)
    lid = assessment["lineage_id"] or f"DISPUTE-{case.dispute_id}"
    if any(
        e.payload["dispute_id"] == case.dispute_id and e.payload.get("option") == option for e in ledger.entries(lid, "dispute_response")
    ):
        raise DisputeAlreadyAnswered(f"{option} already sent for {case.dispute_id}", dispute_id=case.dispute_id)

    money = {"currency_code": case.currency, "value": format(q(case.amount), "f")}
    if chosen["via"] == "provide_evidence":
        d = case.as_dispute().model_copy(update={"lineage_id": lid})
        bundle = build_evidence(ledger, d)
        bundle["paypal_evidence"]["evidences"][0]["notes"] = note[:2000]
        resp = gateway.provide_evidence(
            case.dispute_id, bundle["paypal_evidence"], [(f"{case.dispute_id}-brief.pdf", render_pdf(d, bundle))]
        )
    elif chosen["via"] == "send_message":
        resp = gateway.dispute_action(case.dispute_id, "send_message", {"message": note[:2000]})
    elif chosen["via"] == "make_offer":
        body = {"note": note[:2000], "offer_amount": money, "offer_type": "REFUND_WITH_RETURN", "return_shipping_address": return_address}
        resp = gateway.dispute_action(case.dispute_id, "make_offer", body)
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
            "amount": str(case.amount),
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
