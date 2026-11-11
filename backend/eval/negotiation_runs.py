"""Negotiation evaluation: 20 seeded runs with varied seller parameters, some of them misbehaving.

Sellers are deterministic policies (app/stages/s02_negotiate.SellerAgent), not LLMs or real merchants, so the
savings figure measures the buyer's strategy against simulated concession curves. What this does test for real is
the schema gate: every misbehaving seller must be dropped before it can win.

    python -m eval.negotiation_runs
"""

import asyncio
import random
import statistics
from decimal import Decimal

from app.core.money import q
from app.domain.models import Mandate, Need, Offer
from app.stages import s02_negotiate
from app.stages.s02_negotiate import SellerAgent

SEED = 20261106
RUNS = 20


class Garbage(SellerAgent):
    """Replies with a non-numeric price on turn 2."""

    async def respond(self, turn, buyer_counter, quantity):
        raw = await super().respond(turn, buyer_counter, quantity)
        if turn == 2:
            raw["unit_price"] = "best price, trust me"
        return raw


class ExtraField(SellerAgent):
    """Smuggles an unrequested field into its offer (the schema forbids extras)."""

    async def respond(self, turn, buyer_counter, quantity):
        raw = await super().respond(turn, buyer_counter, quantity)
        raw["note"] = "let's keep chatting"
        return raw


class WalksBack(SellerAgent):
    """Quotes a higher price on turn 3 than it did on turn 2."""

    async def respond(self, turn, buyer_counter, quantity):
        raw = await super().respond(turn, buyer_counter, quantity)
        if turn == 3:
            raw["unit_price"] = str(q(self.list_price * Decimal("1.05")))
        return raw


class WrongQuantity(SellerAgent):
    async def respond(self, turn, buyer_counter, quantity):
        return await super().respond(turn, buyer_counter, quantity + 1)


FAULTY = [Garbage, ExtraField, WalksBack, WrongQuantity]


def scenario(rng: random.Random, i: int):
    baseline = Decimal(rng.randrange(40, 800))
    quantity = rng.randrange(1, 11)
    sellers: list[SellerAgent] = []
    for n in range(rng.randrange(3, 6)):
        list_price = q(baseline * Decimal(str(round(rng.uniform(0.92, 1.18), 3))))
        floor = q(list_price * Decimal(str(round(rng.uniform(0.70, 0.95), 3))))
        sellers.append(
            SellerAgent(
                f"seller-{i}-{n}",
                f"SKU-{i}-{n}",
                list_price,
                floor,
                concession=Decimal(str(round(rng.uniform(0.2, 0.8), 2))),
                return_days=rng.choice([14, 30, 30, 45]),
                ship_days=rng.randrange(1, 8),
            )
        )
    faulty_ids = []
    for _ in range(rng.choice([0, 1, 1, 2])):
        cls = rng.choice(FAULTY)
        n = len(sellers)
        list_price = q(baseline * Decimal(str(round(rng.uniform(0.85, 1.0), 3))))  # tempting: often the cheapest quote
        sellers.append(cls(f"seller-{i}-{n}", f"SKU-{i}-{n}", list_price, q(list_price * Decimal("0.8"))))
        faulty_ids.append(sellers[-1].seller_id)
    mandate = Mandate(
        principal="eval",
        purpose="eval",
        budget=Decimal("100000"),
        auto_threshold=Decimal("1000"),
        per_txn_cap=Decimal("50000"),
        vendor_allowlist=[s.seller_id for s in sellers],
        allowed_categories=["x"],
        min_return_days=rng.choice([14, 30]),
    )
    return mandate, Need(description="x", category="x", quantity=quantity), sellers, baseline, faulty_ids


def run() -> dict:
    rng = random.Random(SEED)
    rows = []
    for i in range(RUNS):
        mandate, need, sellers, baseline, faulty_ids = scenario(rng, i)
        res = asyncio.run(s02_negotiate.negotiate(f"eval-{i}", mandate, need, sellers, baseline))
        offers = [t for t in res.transcript if t.get("from") == "seller"]
        for t in offers:  # everything the buyer ever saw must be a valid Offer
            Offer.model_validate({k: v for k, v in t.items() if k not in ("from",)})
        rows.append(
            {
                "winner": res.winner is not None,
                "savings_pct": float(res.savings_pct) if res.savings_pct is not None else None,
                "turns": max((t["turn"] for t in res.transcript), default=0),
                "faulty": len(faulty_ids),
                "faulty_dropped": sum(f in res.dropped for f in faulty_ids),
                "faulty_won": res.winner is not None and res.winner.seller_id in faulty_ids,
                "commitments": sum(r.status == "COMMITTED" for r in res.book.reservations.values()),
            }
        )
    savings = [r["savings_pct"] for r in rows if r["savings_pct"] is not None]
    return {
        "runs": RUNS,
        "with_winner": sum(r["winner"] for r in rows),
        "mean_savings": round(statistics.mean(savings), 1),
        "median_savings": round(statistics.median(savings), 1),
        "min_savings": min(savings),
        "max_savings": max(savings),
        "in_target_band": sum(12 <= s <= 18 for s in savings),
        "max_turns": max(r["turns"] for r in rows),
        "faulty_total": sum(r["faulty"] for r in rows),
        "faulty_dropped": sum(r["faulty_dropped"] for r in rows),
        "faulty_won": sum(r["faulty_won"] for r in rows),
        "bad_commitments": sum(r["commitments"] > 1 for r in rows),
    }


def table(res: dict) -> str:
    return "\n".join(
        [
            "| Measure | Result |",
            "|---|---|",
            f"| Runs (seeded, varied sellers) | {res['runs']} ({res['with_winner']} produced a winner) |",
            f"| Savings vs baseline | mean {res['mean_savings']}%, median {res['median_savings']}%, "
            f"range {res['min_savings']}% to {res['max_savings']}% |",
            f"| Runs inside the 12 to 18% band | {res['in_target_band']} of {res['with_winner']} |",
            f"| Most turns used | {res['max_turns']} (cap 3) |",
            f"| Misbehaving sellers injected / dropped by the schema gate | {res['faulty_total']} / {res['faulty_dropped']} |",
            f"| Misbehaving sellers that won | {res['faulty_won']} |",
            f"| Runs with more than one commitment | {res['bad_commitments']} |",
        ]
    )


if __name__ == "__main__":
    print(table(run()))
