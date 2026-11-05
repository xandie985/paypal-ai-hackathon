"""Live sandbox probe for dispute offers, using the production code path (s08_defend.offer_body +
SandboxPayPal.dispute_action). Dry run unless --send; sending asks you to type the dispute ID back.

    backend/.venv/bin/python scripts/live_dispute_probe.py list
    backend/.venv/bin/python scripts/live_dispute_probe.py offer PP-R-XXX-12345678 10.00          # dry run
    backend/.venv/bin/python scripts/live_dispute_probe.py offer PP-R-XXX-12345678 10.00 --send   # really send

A partial refund is a money-only REFUND offer below the disputed amount. The probe is a test of PayPal's
API, not an agent decision: it writes nothing to the evidence ledger. Note what you sent in doc 09.
"""

import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.integrations.paypal import PayPalAPIError, SandboxPayPal  # noqa: E402
from app.stages.s08_defend import offer_body, parse_paypal_dispute  # noqa: E402

NOTE = "Hello, we're sorry for the trouble. We're offering a partial refund of {amount} {currency} to settle this."


def gateway(s: Settings) -> SandboxPayPal:
    if not (s.paypal_client_id and s.paypal_client_secret):
        sys.exit("PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET not set in .env")
    if "sandbox" not in s.paypal_base_url:
        sys.exit(f"refusing to probe a non-sandbox PayPal ({s.paypal_base_url})")
    return SandboxPayPal(s.paypal_client_id, s.paypal_client_secret, s.paypal_base_url)


def list_cases(gw) -> None:
    for d in gw.list_disputes():
        c = parse_paypal_dispute(gw.get_dispute(d["dispute_id"]))
        ok = c.status == "WAITING_FOR_SELLER_RESPONSE" and "make_offer" in c.actions
        print(
            f"{c.dispute_id:24} {c.reason:42} {c.stage:10} {c.status:28} {c.amount:>8} {c.currency}"
            f"  offer: {'yes ' + str(c.allowed_offer_types) if ok else 'no'}"
        )


def probe_offer(gw, dispute_id: str, amount: Decimal, send: bool, confirm=input) -> str:
    """Returns PASS / FAIL / DRY_RUN / ABORTED; prints every request and response."""
    raw = gw.get_dispute(dispute_id)
    c = parse_paypal_dispute(raw)
    print(f"case     {c.dispute_id}  {c.reason}  stage={c.stage}  status={c.status}  disputed={c.amount} {c.currency}")
    print(f"allowed  links={c.actions}  offer_types={c.allowed_offer_types}")
    problems = []
    if c.status != "WAITING_FOR_SELLER_RESPONSE":
        problems.append(f"status is {c.status}, PayPal isn't waiting on the seller")
    if "make_offer" not in c.actions:
        problems.append("PayPal doesn't list make_offer for this case (chargeback stages never do)")
    if "REFUND" not in c.allowed_offer_types:
        problems.append(f"REFUND isn't an allowed offer type ({c.allowed_offer_types})")
    if not (Decimal("0") < amount <= c.amount):
        problems.append(f"amount must be above 0 and at most the disputed {c.amount}")
    body = offer_body(c, amount, NOTE.format(amount=amount, currency=c.currency))
    print("body     " + json.dumps(body))
    if problems:
        print("FAIL     preconditions: " + "; ".join(problems))
        return "FAIL"
    kind = "partial" if amount < c.amount else "full"
    if not send:
        print(f"DRY_RUN  would send a {kind} REFUND offer. Re-run with --send to send it.")
        return "DRY_RUN"
    if confirm(f"Send a {kind} refund offer of {amount} {c.currency} on {c.dispute_id}? Type the dispute ID: ").strip() != c.dispute_id:
        print("ABORTED  nothing sent")
        return "ABORTED"
    try:
        resp = gw.dispute_action(c.dispute_id, "make_offer", body)
    except PayPalAPIError as e:
        print(f"FAIL     PayPal {e.status} {e.name} debug_id={e.debug_id} details={json.dumps(e.details)}")
        return "FAIL"
    print("response " + json.dumps(resp)[:400])
    after = parse_paypal_dispute(gw.get_dispute(c.dispute_id))
    print(f"after    status={after.status}  links={after.actions}")
    ok = after.status == "WAITING_FOR_BUYER_RESPONSE"
    print(("PASS     " if ok else "FAIL     ") + f"{kind} refund offer {'accepted by PayPal' if ok else 'sent but status did not move'}")
    return "PASS" if ok else "FAIL"


if __name__ == "__main__":
    args = sys.argv[1:]
    s = Settings(_env_file=ROOT / ".env")
    if args[:1] == ["list"]:
        list_cases(gateway(s))
    elif args[:1] == ["offer"] and len(args) >= 3:
        try:
            amt = Decimal(args[2])
        except InvalidOperation:
            sys.exit(f"not an amount: {args[2]}")
        result = probe_offer(gateway(s), args[1], amt, "--send" in args)
        sys.exit(0 if result in ("PASS", "DRY_RUN") else 1)
    else:
        sys.exit(__doc__)
