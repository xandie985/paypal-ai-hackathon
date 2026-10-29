"""Penny-exact money. PayPal rejects an order with AMOUNT_MISMATCH when
amount.value != item_total + tax_total + shipping - discount, or when item_total /
tax_total don't equal the per-item sums. We build the breakdown from per-unit
rounded values so those identities hold by construction, then assert them anyway."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .errors import AmountMismatch

CENT = Decimal("0.01")


def q(x) -> Decimal:
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def _money(currency: str, value: Decimal) -> dict:
    return {"currency_code": currency, "value": format(q(value), "f")}


@dataclass(frozen=True)
class LineItem:
    name: str
    sku: str
    unit_amount: Decimal
    quantity: int
    tax_rate: Decimal = Decimal("0")

    @property
    def unit_tax(self) -> Decimal:
        return q(q(self.unit_amount) * self.tax_rate)


def build_purchase_unit(
    items: list[LineItem], currency: str, lineage_id: str, shipping: Decimal = Decimal("0"), description: str = ""
) -> dict:
    item_total = sum((q(i.unit_amount) * i.quantity for i in items), Decimal("0"))
    tax_total = sum((i.unit_tax * i.quantity for i in items), Decimal("0"))
    total = item_total + tax_total + q(shipping)
    pu = {
        "reference_id": lineage_id[:256],
        "custom_id": lineage_id[:127],
        "description": description[:127],
        "amount": {
            **_money(currency, total),
            "breakdown": {
                "item_total": _money(currency, item_total),
                "tax_total": _money(currency, tax_total),
                "shipping": _money(currency, shipping),
            },
        },
        "items": [
            {
                "name": i.name[:127],
                "sku": i.sku[:127],
                "quantity": str(i.quantity),
                "unit_amount": _money(currency, i.unit_amount),
                "tax": _money(currency, i.unit_tax),
            }
            for i in items
        ],
    }
    assert_breakdown_consistent(pu)
    return pu


def assert_breakdown_consistent(pu: dict) -> None:
    amt = pu["amount"]
    b = amt["breakdown"]
    d = lambda m: Decimal(m["value"])  # noqa: E731
    items_sum = sum((d(i["unit_amount"]) * int(i["quantity"]) for i in pu.get("items", [])), Decimal("0"))
    tax_sum = sum((d(i["tax"]) * int(i["quantity"]) for i in pu.get("items", []) if "tax" in i), Decimal("0"))
    expected = (
        d(b["item_total"])
        + d(b.get("tax_total", {"value": "0"}))
        + d(b.get("shipping", {"value": "0"}))
        - d(b.get("discount", {"value": "0"}))
    )
    problems = []
    if items_sum != d(b["item_total"]):
        problems.append(f"item_total {b['item_total']['value']} != sum(items) {items_sum}")
    if "tax_total" in b and tax_sum != d(b["tax_total"]):
        problems.append(f"tax_total {b['tax_total']['value']} != sum(item tax) {tax_sum}")
    if expected != d(amt):
        problems.append(f"amount {amt['value']} != breakdown {expected}")
    if problems:
        raise AmountMismatch("; ".join(problems))


def gross_to_net(gross: Decimal, fee_pct: Decimal, fee_fixed: Decimal, fx_rate: Decimal = Decimal("1")) -> dict:
    """Payee-side view of a payout: what arrives after fees and FX."""
    gross = q(gross)
    fee = q(gross * fee_pct + fee_fixed)
    net = q(gross - fee)
    return {"gross": gross, "fee": fee, "net": net, "fx_rate": fx_rate, "net_converted": q(net * fx_rate)}
