"""Stage 2b - NEGOTIATE. Buyer agent vs N seller agents, strictly 3 turns:
quote -> counter -> best-and-final. Fixes blocker B2b:

- polite loops: hard turn cap, no free-form chat
- bad JSON: every seller turn passes the Offer schema gate or the seller is dropped
- double commitment: reserve-then-commit (CANO) through ReservationBook
"""

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal

from pydantic import ValidationError

from ..core.canonical import sha256_hex
from ..core.errors import DoubleCommitment
from ..core.money import q
from ..domain.models import Mandate, Need, Offer

MAX_TURNS = 3
ACTIONS = {1: "quote", 2: "counter", 3: "final"}


@dataclass
class SellerAgent:
    """Deterministic seller policy. Swap `respond` for an LLM-backed seller later;
    its output still has to pass `schema_gate`."""

    seller_id: str
    sku: str
    list_price: Decimal
    floor_price: Decimal
    concession: Decimal = Decimal("0.5")  # share of the gap to the buyer's counter conceded per turn
    return_days: int = 30
    ship_days: int = 3
    terms: str = "Standard warranty."
    _last: Decimal | None = None

    async def respond(self, turn: int, buyer_counter: Decimal | None, quantity: int) -> dict:
        if turn == 1 or buyer_counter is None:
            price = self.list_price
        else:
            prev = self._last or self.list_price
            price = max(self.floor_price, prev - (prev - buyer_counter) * self.concession)
        self._last = q(price)
        return {
            "seller_id": self.seller_id,
            "sku": self.sku,
            "turn": turn,
            "action": ACTIONS[turn],
            "unit_price": str(self._last),
            "quantity": quantity,
            "return_days": self.return_days,
            "ship_days": self.ship_days,
            "terms": self.terms,
        }


def schema_gate(raw: dict, expected_turn: int, quantity: int, previous: Offer | None) -> Offer | None:
    """Parse untrusted seller output. Returns None (seller dropped) on any violation."""
    try:
        offer = Offer.model_validate(raw)
    except ValidationError:
        return None
    if offer.turn != expected_turn or offer.quantity != quantity:
        return None
    if previous and offer.unit_price > previous.unit_price:  # a seller may not walk its price back up
        return None
    return offer


@dataclass
class Reservation:
    reservation_id: str
    offer: Offer
    status: str = "RESERVED"  # RESERVED -> COMMITTED | CANCELLED


@dataclass
class ReservationBook:
    """Reserve every acceptable final offer, commit exactly one, cancel the rest."""

    session_id: str
    reservations: dict[str, Reservation] = field(default_factory=dict)

    def reserve(self, offer: Offer) -> Reservation:
        rid = f"rsv-{sha256_hex([self.session_id, offer])[:12]}"
        self.reservations.setdefault(rid, Reservation(rid, offer))
        return self.reservations[rid]

    def commit(self, reservation_id: str) -> Reservation:
        committed = [r for r in self.reservations.values() if r.status == "COMMITTED"]
        if committed and committed[0].reservation_id != reservation_id:
            raise DoubleCommitment(
                "another seller is already committed for this negotiation",
                session_id=self.session_id,
                committed=committed[0].offer.seller_id,
            )
        r = self.reservations[reservation_id]
        if r.status == "CANCELLED":
            raise DoubleCommitment("reservation was cancelled", reservation_id=reservation_id)
        r.status = "COMMITTED"
        for other in self.reservations.values():
            if other.reservation_id != reservation_id:
                other.status = "CANCELLED"
        return r


@dataclass
class NegotiationResult:
    session_id: str
    winner: Offer | None
    reservation: Reservation | None
    book: ReservationBook
    transcript: list[dict]
    dropped: list[str]
    baseline_unit_price: Decimal | None
    savings_pct: Decimal | None
    commitment_hash: str | None


def _buyer_counter(best: Decimal, baseline: Decimal | None, turn: int) -> Decimal:
    anchor = min(best, baseline) if baseline else best
    return q(anchor * (Decimal("0.80") if turn == 2 else Decimal("0.88")))


async def negotiate(
    session_id: str, mandate: Mandate, need: Need, sellers: list[SellerAgent], baseline: Decimal | None
) -> NegotiationResult:
    transcript, dropped = [], []
    last: dict[str, Offer] = {}
    active = list(sellers)
    counter: Decimal | None = None

    for turn in range(1, MAX_TURNS + 1):
        raws = await asyncio.gather(*(s.respond(turn, counter, need.quantity) for s in active))
        still = []
        for seller, raw in zip(active, raws, strict=True):
            offer = schema_gate(raw, turn, need.quantity, last.get(seller.seller_id))
            if offer is None:
                dropped.append(seller.seller_id)
                transcript.append({"turn": turn, "seller_id": seller.seller_id, "event": "dropped_by_schema_gate"})
                continue
            last[seller.seller_id] = offer
            still.append(seller)
            transcript.append({"turn": turn, "from": "seller", **offer.model_dump(mode="json")})
        active = still
        if not active:
            break
        if turn < MAX_TURNS:
            counter = _buyer_counter(min(last[s.seller_id].unit_price for s in active), baseline, turn + 1)
            transcript.append({"turn": turn + 1, "from": "buyer", "action": "counter", "unit_price": str(counter)})

    book = ReservationBook(session_id)
    finals = [last[s.seller_id] for s in active]
    eligible = [
        o
        for o in finals
        if o.seller_id in mandate.vendor_allowlist
        and o.return_days >= mandate.min_return_days
        and (need.max_unit_price is None or o.unit_price <= need.max_unit_price)
    ]
    for o in eligible:
        book.reserve(o)
    if not eligible:
        return NegotiationResult(session_id, None, None, book, transcript, dropped, baseline, None, None)

    winner = min(eligible, key=lambda o: (o.unit_price, o.ship_days))
    reservation = next(r for r in book.reservations.values() if r.offer == winner)
    book.commit(reservation.reservation_id)
    savings = q((baseline - winner.unit_price) / baseline * 100) if baseline else None
    return NegotiationResult(
        session_id,
        winner,
        reservation,
        book,
        transcript,
        dropped,
        baseline,
        savings,
        sha256_hex({"session": session_id, "offer": winner}),
    )
