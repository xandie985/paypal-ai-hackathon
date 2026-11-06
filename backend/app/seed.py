"""Seeded history: ~30 synthetic mandates run through the real step functions, in replay.

Every row comes from the same code path as a live run (runs.step_*, the firewall, settlement,
stage 5 delivery proof, the stage 8 dispute desk, stage 10 calibration). Only the inputs are
synthetic: mandates, needs, seller prices and buyer behaviour, drawn from a seeded RNG so the
history is the same on every build. Timestamps are spread over past days with an injected ledger
clock; they are inside the hash chain, so the history ledger verifies like any other.

Nothing here touches PayPal or Channel3: the gateways are always the replay doubles.
"""

import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from .config import Settings
from .core.errors import GuardViolation
from .core.ledger import EvidenceLedger
from .domain.models import DeliveryReport, Mandate, Need
from .integrations.channel3 import LIVE_DEMO_MERCHANTS, ReplayChannel3
from .integrations.paypal import ReplayPayPal
from .orchestrator import Runtime
from .runs import (
    Run,
    step_approve,
    step_attack,
    step_capture_order,
    step_delegate,
    step_discover_and_negotiate,
    step_govern,
    step_prepare_order,
    step_reject,
)
from .stages import s05_verify, s08_defend, s10_learn
from .stages.s02_negotiate import SellerAgent

SEED = 7
MANDATES = 30
DAYS = 30
APPROVER = "seeded-history"

VENDORS = ["Northwind Displays", "Contoso Retail", "Fabrikam Outlet"]
NEEDS = [
    ("1080p webcam", "webcams", "direct", (1, 4)),
    ("27in 4K monitor", "monitors", "negotiate", (2, 4)),
    ("USB condenser microphone", "microphones", "direct", (1, 2)),
]
BUYER_NOTES = {
    "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED": "it stopped working after a week",
    "MERCHANDISE_OR_SERVICE_NOT_RECEIVED": "my order never arrived",
    "DUPLICATE_TRANSACTION": "i was charged twice",
    "INCORRECT_AMOUNT": "the amount is not what i agreed to",
}


class SeedClock:
    """Monotonic fake clock: each ledger entry advances it a few minutes."""

    def __init__(self, start: datetime, rng: random.Random):
        self.t, self.rng = start, rng

    def __call__(self) -> datetime:
        self.t += timedelta(minutes=self.rng.randint(1, 12), seconds=self.rng.randint(0, 59))
        return self.t

    def jump_to(self, t: datetime) -> None:
        self.t = max(self.t, t)


def _sellers(rng: random.Random) -> list[SellerAgent]:
    """Simulated negotiators with jittered prices; sometimes one that emits malformed turns."""
    j = lambda x: (Decimal(x) * Decimal(str(round(rng.uniform(0.92, 1.08), 3)))).quantize(Decimal("0.01"))  # noqa: E731
    out = [
        SellerAgent("Northwind Displays", "NW-27-4K", j("389"), j("340"), terms="30-day returns, 3-year warranty."),
        SellerAgent("Contoso Retail", "CR-27-4K", j("412"), j("350"), terms="30-day returns, 1-year warranty."),
        SellerAgent("Fabrikam Outlet", "FB-27-RF", j("299"), j("260"), return_days=14, terms="Refurbished. 14-day returns."),
    ]
    if rng.random() < 0.3:
        from .orchestrator import MalformedSeller

        out.append(MalformedSeller("Globex Wholesale", "GX-27", j("370"), j("330")))
    return out


def _mandate(rng: random.Random, i: int) -> Mandate:
    threshold = Decimal(rng.choice(["150", "200", "300", "500"]))
    return Mandate(
        principal=f"buyer{i:02d}@seeded.example",
        purpose=f"Seeded office purchase #{i:02d}",
        budget=Decimal(rng.choice(["800", "1500", "2200", "3000"])),
        auto_threshold=threshold,
        per_txn_cap=Decimal(rng.choice(["1000", "1500", "2000"])),
        vendor_allowlist=rng.sample(VENDORS, k=rng.choice([2, 2, 3])) + LIVE_DEMO_MERCHANTS,
        allowed_categories=rng.sample(["monitors", "webcams", "microphones"], k=rng.choice([2, 3, 3])),
        min_return_days=rng.choice([14, 30, 30]),
        mode="review_first" if rng.random() < 0.1 else "auto",
    )


def _dispute(run: Run, item, rng: random.Random, clock: SeedClock) -> None:
    """A buyer disputes a settled item; the desk assesses; we send its recommendation; PayPal decides."""
    gw, led = run.rt.gateway, run.rt.ledger
    reason = rng.choice(list(BUYER_NOTES))
    opened = clock()
    raw = gw.open_dispute(
        lineage_id=item.lineage_id,
        capture_id=item.capture["id"],
        amount=item.capture["amount"]["value"],
        reason=reason,
        note=BUYER_NOTES[reason],
        item_name=item.title,
        due=(opened + timedelta(days=10)).date().isoformat(),
        created=opened.isoformat(),
    )
    case = s08_defend.parse_paypal_dispute(raw)
    today = clock().date()
    a = s08_defend.assess(case, led, item.lineage_id, today, return_address_set=True)
    option = a["recommended"]
    if not option:
        return
    note = s08_defend.draft_reply(case, a, option)
    try:
        s08_defend.respond(gw, led, case, a, option=option, note=note, approver=APPROVER, return_address=run.rt.settings.return_address)
    except GuardViolation:
        return
    if option == "contest":
        won = rng.random() < a["win_odds"]
        gw.resolve_dispute(case.dispute_id, "RESOLVED_SELLER_FAVOUR" if won else "RESOLVED_BUYER_FAVOUR")
    elif gw.get_dispute(case.dispute_id)["status"] != "RESOLVED":
        gw.resolve_dispute(case.dispute_id, "RESOLVED_BUYER_FAVOUR")  # the buyer takes the refund we offered
    clock()
    s08_defend.sync_outcome(led, s08_defend.parse_paypal_dispute(gw.get_dispute(case.dispute_id)), item.lineage_id)


async def _one_mandate(rt: Runtime, i: int, rng: random.Random, clock: SeedClock) -> None:
    run = Run(f"seed{i:02d}-{uuid.UUID(int=rng.getrandbits(128)).hex[:6]}", rt, _mandate(rng, i))
    step_delegate(run)
    for desc, cat, method, (lo, hi) in rng.sample(NEEDS, k=rng.randint(1, 3)):
        need = Need(description=desc, category=cat, quantity=rng.randint(lo, hi))
        try:
            item = await step_discover_and_negotiate(run, need, method, sellers=_sellers(rng))
        except ValueError:
            continue  # no allowlisted seller survived: nothing to buy, as in a live run
        run.items[item.lineage_id] = item
        step_govern(run, item)
        if item.status == "awaiting_approval":
            if rng.random() < 0.8:
                step_approve(run, item.lineage_id, APPROVER)
            else:
                step_reject(run, item.lineage_id, APPROVER, rng.choice(["over budget this quarter", "prefer another vendor"]))
        if item.status == "authorized":
            try:
                step_prepare_order(run, item.lineage_id)
                step_capture_order(run, item.lineage_id)
            except GuardViolation:
                continue
        if item.status != "settled":
            continue
        due = (clock.t + timedelta(days=4)).date()
        roll = rng.random()
        status, on = (
            ("DELIVERED", due - timedelta(days=1))
            if roll < 0.8
            else ("DELIVERED", due + timedelta(days=2))
            if roll < 0.9
            else ("LOST", None)
        )
        s05_verify.verify_delivery(
            rt.ledger,
            rt.settings.gate_secret,
            item.lineage_id,
            item.prep["order"]["id"],
            DeliveryReport(
                carrier=rng.choice(["UPS", "FedEx", "DHL"]),
                tracking_number=f"SEED{rng.randint(10**7, 10**8)}",
                tracking_status=status,
                delivered_on=on.isoformat() if on else None,
                due_by=due.isoformat(),
            ),
        )
        if rng.random() < 0.2:
            _dispute(run, item, rng, clock)
    if rng.random() < 0.25:
        step_attack(run)
    s10_learn.calibrate(rt.ledger, run.mandate, run.mandate_lineage)


def build_history(n: int = MANDATES, seed: int = SEED, days: int = DAYS, now: datetime | None = None) -> EvidenceLedger:
    """Deterministic for a given seed and `now`: same inputs, same decisions, same rows."""
    rng = random.Random(seed)
    end = (now or datetime.now(UTC)).replace(microsecond=0)
    start = end - timedelta(days=days)
    clock = SeedClock(start, rng)
    ledger = EvidenceLedger(":memory:", clock=clock)
    settings = Settings(_env_file=None, replay_mode=True)  # never live, whatever .env says
    rt = Runtime(settings, ledger, ReplayPayPal(), ReplayChannel3())

    async def go():
        for i in range(n):
            clock.jump_to(start + timedelta(days=(days - 1) * i / n, hours=rng.randint(8, 12)))  # stays in the past
            await _one_mandate(rt, i, rng, clock)

    asyncio.run(go())
    return ledger
