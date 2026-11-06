"""PayPal account data for the Command Center's "PayPal overview" pages (GET /api/studio/paypal).

Adapted from paypaldev/hackathon-paypal-ag-grid-boilerplate (lib/paypal.ts, lib/dashboard-data.ts): the same
related tables (customers, invoices, invoice line items, invoice payments, products, plans, transactions,
payouts, balances), built from PayPal REST responses. Live mode reads the sandbox account through
SandboxPayPal; replay mode builds the same tables from a small fixed set of PayPal-shaped responses, so the
public demo and the tests need no network and run the same transformation code as live.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException

from .config import settings
from .integrations.paypal import PayPalAPIError, SandboxPayPal, make_gateway

router = APIRouter(prefix="/api")

TRANSACTION_SEARCH_MAX_DAYS = 31  # Transaction Search rejects longer ranges
FIXTURE_AS_OF = datetime(2026, 11, 5, 12, 0, 0, tzinfo=UTC)  # fixed, so the replay tables never drift
CACHE_TTL_S = 60.0  # a live read is ~N+1 requests; reloads inside this window reuse it


def _round2(n: float) -> float:
    return round(n * 100) / 100


def _amount(m: dict | None) -> float:
    """PayPal sends money as {"value": "12.50", "currency_code": "USD"}; a missing amount counts as 0."""
    return float(m["value"]) if m and m.get("value") is not None else 0.0


def _humanise(code: str) -> str:
    return code[:1] + code[1:].lower().replace("_", " ")


def _days_between(start: str, end: str) -> int:
    return round((datetime.fromisoformat(end[:10]) - datetime.fromisoformat(start[:10])).days)


# ---- live reads ----------------------------------------------------------------------------------


def _list_all(gw: SandboxPayPal, path: str, key: str, page_size: int, params: dict | None = None) -> list[dict]:
    """Follow `page`/`total_pages`. The first request must carry whatever flag makes the endpoint report them."""
    items: list[dict] = []
    page = 1
    while True:
        body = gw.get_json(path, {**(params or {}), "page_size": page_size, "page": page})
        items += body.get(key) or []
        if page >= (body.get("total_pages") or 1):
            return items
        page += 1


def _details(gw: SandboxPayPal, path: str, key: str, page_size: int, params: dict | None = None) -> list[dict]:
    """List endpoints return summaries (no line items, billing cycles, product type), so fetch each record."""
    summaries = _list_all(gw, path, key, page_size, params)
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda s: gw.get_json(f"{path}/{s['id']}"), summaries))


def fetch_account(gw: SandboxPayPal, as_of: datetime) -> dict:
    """Raw PayPal responses for the account: products, plans, invoices, transactions and balances."""
    iso = lambda d: d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731 (no fractional seconds allowed)
    return {
        "products": _details(gw, "/v1/catalogs/products", "products", 20, {"total_required": "true"}),
        "plans": _details(gw, "/v1/billing/plans", "plans", 20, {"total_required": "true"}),
        "invoices": _details(gw, "/v2/invoicing/invoices", "items", 100, {"total_required": "true"}),
        "transactions": _list_all(
            gw,
            "/v1/reporting/transactions",
            "transaction_details",
            500,
            {"start_date": iso(as_of - timedelta(days=TRANSACTION_SEARCH_MAX_DAYS)), "end_date": iso(as_of), "fields": "all"},
        ),
        "balances": gw.get_json("/v1/reporting/balances"),
    }


# ---- tables --------------------------------------------------------------------------------------

_STATUS_GROUP = {
    "DRAFT": "Draft",
    "SCHEDULED": "Scheduled",
    "SENT": "Open",
    "UNPAID": "Open",
    "PAYMENT_PENDING": "Open",
    "PARTIALLY_PAID": "Partially paid",
    "PAID": "Paid",
    "MARKED_AS_PAID": "Paid",
    "REFUNDED": "Refunded",
    "PARTIALLY_REFUNDED": "Refunded",
    "MARKED_AS_REFUNDED": "Refunded",
    "CANCELLED": "Cancelled",
}
_UNISSUED = {"DRAFT", "SCHEDULED", "CANCELLED"}  # not sent, or withdrawn: nothing was billed
_RECEIVABLE = {"SENT", "UNPAID", "PAYMENT_PENDING", "PARTIALLY_PAID"}
_MONTHS_PER_INTERVAL = {"DAY": 12 / 365, "WEEK": 12 / 52, "MONTH": 1, "YEAR": 12}
_DAYS_PER_INTERVAL = {"DAY": 1, "WEEK": 7, "MONTH": 365 / 12, "YEAR": 365}
_EVENT_TYPES = {"T0001": "Payout", "T1105": "Hold released", "T1503": "Payout hold"}
_TXN_STATUSES = {"S": "Success", "P": "Pending", "D": "Denied", "V": "Reversed", "F": "Partially refunded"}


def _billing(inv: dict) -> dict:
    return ((inv.get("primary_recipients") or [{}])[0]).get("billing_info") or {}


def _customer_id(inv: dict) -> str:
    """Customers have no id of their own in PayPal, so invoices are matched to them by email."""
    return (_billing(inv).get("email_address") or "unknown").lower()


def _aging_bucket(days_overdue: int) -> str:
    # Numbered so the buckets sort in age order on chart axes.
    if days_overdue <= 0:
        return "0. Not yet due"
    if days_overdue <= 30:
        return "1. 1-30 days"
    if days_overdue <= 60:
        return "2. 31-60 days"
    if days_overdue <= 90:
        return "3. 61-90 days"
    return "4. 90+ days"


def _invoice_row(inv: dict, today: str) -> dict:
    status = inv["status"]
    detail = inv["detail"]
    total = _amount(inv.get("amount"))
    paid = _amount((inv.get("payments") or {}).get("paid_amount"))
    refunded = _amount((inv.get("refunds") or {}).get("refund_amount"))
    receivable = status in _RECEIVABLE
    outstanding = _amount(inv.get("due_amount")) if receivable else 0.0
    term = detail.get("payment_term") or {}
    due_date = term.get("due_date") or detail.get("invoice_date")
    days_overdue = max(0, _days_between(due_date, today)) if receivable and due_date else 0
    pay_dates = sorted(t["payment_date"] for t in (inv.get("payments") or {}).get("transactions") or [] if t.get("payment_date"))
    return {
        "id": inv["id"],
        "number": detail["invoice_number"],
        "customerId": _customer_id(inv),
        "status": _humanise(status),
        "statusGroup": _STATUS_GROUP[status],
        "currency": detail["currency_code"],
        "paymentTerm": _humanise(term["term_type"]) if term.get("term_type") else None,
        "invoiceDate": detail.get("invoice_date"),
        "dueDate": due_date,
        "total": total,
        "issuedAmount": 0.0 if status in _UNISSUED else total,
        "paidAmount": paid,
        "refundedAmount": refunded,
        "netCollected": _round2(paid - refunded),
        "isReceivable": receivable,
        "outstanding": outstanding,
        "overdueAmount": outstanding if days_overdue > 0 else 0.0,
        "daysOverdue": days_overdue,
        "agingBucket": _aging_bucket(days_overdue) if receivable else None,
        "daysToPay": _days_between(detail["invoice_date"], pay_dates[0]) if pay_dates and detail.get("invoice_date") else None,
        "taxTotal": _amount(((inv.get("amount") or {}).get("breakdown") or {}).get("tax_total")),
    }


def _customer_rows(invoices: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for inv in invoices:
        cid = _customer_id(inv)
        if cid not in by_id:
            info = _billing(inv)
            by_id[cid] = {
                "id": cid,
                "name": (info.get("name") or {}).get("full_name") or info.get("email_address") or "Unknown",
                # Individuals have no business name; label them so company charts stay readable.
                "company": info.get("business_name") or "Individual",
                "email": info.get("email_address"),
            }
    return list(by_id.values())


def _item_rows(invoices: list[dict]) -> list[dict]:
    rows = []
    for inv in invoices:
        for i, item in enumerate(inv.get("items") or [], 1):
            gross = float(item["quantity"]) * _amount(item["unit_amount"])
            disc = item.get("discount") or {}
            discount = _amount(disc["amount"]) if disc.get("amount") else gross * float(disc.get("percent") or 0) / 100
            tx = item.get("tax") or {}
            tax = _amount(tx["amount"]) if tx.get("amount") else (gross - discount) * float(tx.get("percent") or 0) / 100
            rows.append(
                {
                    "id": item.get("id") or f"{inv['id']}-{i}",
                    "invoiceId": inv["id"],
                    "name": item["name"],
                    "unit": _humanise(item["unit_of_measure"]) if item.get("unit_of_measure") else None,
                    "quantity": float(item["quantity"]),
                    "unitPrice": _amount(item["unit_amount"]),
                    "gross": _round2(gross),
                    "discount": _round2(discount),
                    "tax": _round2(tax),
                    "lineTotal": _round2(gross - discount + tax),
                }
            )
    return rows


def _payment_rows(invoices: list[dict]) -> list[dict]:
    rows = []
    for inv in invoices:
        for kind, block, id_key, date_key, sign in (
            ("Payment", inv.get("payments"), "payment_id", "payment_date", 1),
            ("Refund", inv.get("refunds"), "recipient_transaction_id", "refund_date", -1),
        ):
            for i, t in enumerate((block or {}).get("transactions") or [], 1):
                amount = _amount(t["amount"])
                rows.append(
                    {
                        "id": t.get(id_key) or f"{inv['id']}-{kind.lower()}-{i}",
                        "invoiceId": inv["id"],
                        "kind": kind,
                        "method": _humanise(t["method"]) if t.get("method") else "Unknown",
                        "date": t.get(date_key),
                        "amount": amount,
                        "signedAmount": sign * amount,
                    }
                )
    return rows


def _product_rows(products: list[dict]) -> list[dict]:
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "type": _humanise(p["type"]) if p.get("type") else None,
            "category": _humanise(p["category"]) if p.get("category") else None,
            "description": p.get("description"),
        }
        for p in products
    ]


def _plan_rows(plans: list[dict]) -> list[dict]:
    rows = []
    for plan in plans:
        cycles = plan.get("billing_cycles") or []
        regular = next((c for c in cycles if c.get("tenure_type") == "REGULAR"), None)
        trial = next((c for c in cycles if c.get("tenure_type") == "TRIAL"), None)
        fixed = ((regular or {}).get("pricing_scheme") or {}).get("fixed_price")
        price = _amount(fixed) if fixed else None
        freq = (regular or {}).get("frequency") or {}
        unit, count = freq.get("interval_unit"), freq.get("interval_count") or 1
        rows.append(
            {
                "id": plan["id"],
                "productId": plan["product_id"],
                "name": plan["name"],
                "status": _humanise(plan["status"]),
                "billingInterval": None if not unit else (f"Every {unit.lower()}" if count == 1 else f"Every {count} {unit.lower()}s"),
                "price": price,
                "monthlyPrice": _round2(price / (count * _MONTHS_PER_INTERVAL[unit])) if price is not None and unit else None,
                "trialDays": round(trial["frequency"]["interval_count"] * _DAYS_PER_INTERVAL[trial["frequency"]["interval_unit"]])
                if trial
                else 0,
                "setupFee": _amount((plan.get("payment_preferences") or {}).get("setup_fee")),
            }
        )
    return rows


def _txn_status(code: str | None) -> str | None:
    return _TXN_STATUSES.get(code, code) if code else None


def _transaction_rows(transactions: list[dict]) -> list[dict]:
    rows = []
    for d in transactions:
        t, payer = d["transaction_info"], d.get("payer_info") or {}
        amt, fee = _amount(t.get("transaction_amount")), _amount(t.get("fee_amount"))
        code = t.get("transaction_event_code") or ""
        rows.append(
            {
                "id": t["transaction_id"],
                "date": t.get("transaction_initiation_date"),
                "eventType": _EVENT_TYPES.get(code) or code or "Unknown",
                "status": _txn_status(t.get("transaction_status")),
                "direction": "Debit" if amt < 0 else "Credit",
                "currency": (t.get("transaction_amount") or {}).get("currency_code"),
                "amount": amt,
                "fee": fee,
                "net": _round2(amt + fee),
                "endingBalance": _amount(t["ending_balance"]) if t.get("ending_balance") else None,
                "counterparty": payer.get("email_address"),
                "note": t.get("transaction_note"),
            }
        )
    return rows


def _campaign(custom_field: str | None) -> str:
    """Payout custom fields are '<CAMPAIGN>-<yyyy-mm>-<n>', e.g. 'AGGRID-AFFILIATES-2026-09-1'."""
    parts = (custom_field or "").split("-")
    return _humanise(parts[1]) if len(parts) > 2 and parts[0] == "AGGRID" and parts[1].isalpha() and parts[1].isupper() else "Other"


def _payout_rows(transactions: list[dict]) -> list[dict]:
    """Payouts as positive amounts, so they size treemap tiles and pie slices."""
    rows = []
    for d in transactions:
        t, payer = d["transaction_info"], d.get("payer_info") or {}
        if t.get("transaction_event_code") != "T0001":
            continue
        rows.append(
            {
                "id": t["transaction_id"],
                "campaign": _campaign(t.get("custom_field")),
                "recipient": payer.get("email_address") or "Unknown",
                "date": t.get("transaction_initiation_date"),
                "status": _txn_status(t.get("transaction_status")),
                "amount": -_amount(t.get("transaction_amount")),
                "fee": -_amount(t.get("fee_amount")),
                "note": t.get("transaction_note"),
            }
        )
    return rows


def _balance_rows(balances: dict) -> list[dict]:
    return [
        {
            "currency": b["currency"],
            "total": _amount(b.get("total_balance")),
            "available": _amount(b.get("available_balance")),
            "withheld": _amount(b.get("withheld_balance")),
        }
        for b in balances.get("balances") or []
    ]


def build_tables(raw: dict, as_of: datetime) -> dict:
    invoices, transactions = raw["invoices"], raw["transactions"]
    return {
        "asOf": as_of.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "customers": _customer_rows(invoices),
        "invoices": [_invoice_row(i, as_of.astimezone(UTC).date().isoformat()) for i in invoices],
        "invoiceItems": _item_rows(invoices),
        "invoicePayments": _payment_rows(invoices),
        "products": _product_rows(raw["products"]),
        "plans": _plan_rows(raw["plans"]),
        "transactions": _transaction_rows(transactions),
        "payouts": _payout_rows(transactions),
        "balances": _balance_rows(raw["balances"]),
    }


# ---- replay fixture ------------------------------------------------------------------------------


def _usd(value: str, currency: str = "USD") -> dict:
    return {"value": value, "currency_code": currency}


def _fixture_invoice(
    n: int,
    status: str,
    who: tuple[str, str | None, str],
    date: str,
    due: str,
    lines: list[tuple[str, str, str, str]],
    total: str,
    *,
    currency: str = "USD",
    paid: tuple[str, str, str] | None = None,  # (amount, date, method)
    due_amount: str | None = None,
    refund: tuple[str, str] | None = None,  # (amount, date)
) -> dict:
    name, business, email = who
    billing: dict = {"name": {"full_name": name}, "email_address": email}
    if business:
        billing["business_name"] = business
    inv: dict = {
        "id": f"INV2-FIXT-{n:04d}",
        "status": status,
        "detail": {
            "invoice_number": f"PG-{1000 + n}",
            "currency_code": currency,
            "invoice_date": date,
            "payment_term": {"term_type": "NET_30", "due_date": due},
        },
        "primary_recipients": [{"billing_info": billing}],
        "items": [
            {"name": nm, "quantity": q, "unit_amount": _usd(price, currency), "unit_of_measure": unit} for nm, q, price, unit in lines
        ],
        "amount": {**_usd(total, currency), "breakdown": {"tax_total": _usd("0.00", currency)}},
    }
    if due_amount is not None:
        inv["due_amount"] = _usd(due_amount, currency)
    if paid:
        inv["payments"] = {
            "paid_amount": _usd(paid[0], currency),
            "transactions": [
                {"payment_id": f"PAY-FIXT-{n:04d}", "payment_date": paid[1], "method": paid[2], "amount": _usd(paid[0], currency)}
            ],
        }
    if refund:
        inv["refunds"] = {
            "refund_amount": _usd(refund[0], currency),
            "transactions": [
                {
                    "recipient_transaction_id": f"REF-FIXT-{n:04d}",
                    "refund_date": refund[1],
                    "method": "BANK_TRANSFER",
                    "amount": _usd(refund[0], currency),
                }
            ],
        }
    return inv


def _fixture_payout(n: int, day: str, amount: str, fee: str, email: str, campaign: str, balance: str) -> dict:
    return {
        "transaction_info": {
            "transaction_id": f"TXN-FIXT-{n:04d}",
            "transaction_event_code": "T0001",
            "transaction_initiation_date": f"{day}T10:{n:02d}:00+0000",
            "transaction_amount": _usd(f"-{amount}"),
            "fee_amount": _usd(f"-{fee}"),
            "transaction_status": "S",
            "ending_balance": _usd(balance),
            "transaction_note": f"{campaign.title()} payout",
            "custom_field": f"AGGRID-{campaign}-2026-10-{n}",
        },
        "payer_info": {"email_address": email},
    }


def fixture_account() -> dict:
    """PayPal-shaped responses for a small merchant that sells subscriptions, sends invoices and pays affiliates."""
    acme, globex, initech = (
        ("Ada Lovelace", "Acme Robotics", "ada@acme.example"),
        ("Grace Hopper", "Globex GmbH", "grace@globex.example"),
        ("Alan Turing", "Initech", "alan@initech.example"),
    )
    solo = ("Katherine Johnson", None, "katherine@example.com")
    lines = [("Analyst seat", "10", "49.00", "QUANTITY"), ("Onboarding", "1", "250.00", "AMOUNT")]
    invoices = [
        _fixture_invoice(1, "PAID", acme, "2026-08-04", "2026-09-03", lines, "740.00", paid=("740.00", "2026-08-20", "BANK_TRANSFER")),
        _fixture_invoice(
            2,
            "PAID",
            globex,
            "2026-09-02",
            "2026-10-02",
            [("Analyst seat", "20", "45.00", "QUANTITY")],
            "900.00",
            currency="EUR",
            paid=("900.00", "2026-09-25", "CREDIT_CARD"),
        ),
        _fixture_invoice(
            3,
            "PARTIALLY_PAID",
            initech,
            "2026-09-10",
            "2026-10-10",
            lines,
            "740.00",
            paid=("300.00", "2026-09-28", "CHECK"),
            due_amount="440.00",
        ),
        _fixture_invoice(
            4, "UNPAID", acme, "2026-10-20", "2026-11-19", [("Analyst seat", "12", "49.00", "QUANTITY")], "588.00", due_amount="588.00"
        ),
        _fixture_invoice(
            5,
            "SENT",
            globex,
            "2026-10-20",
            "2026-11-19",
            [("Analyst seat", "20", "45.00", "QUANTITY")],
            "900.00",
            currency="EUR",
            due_amount="900.00",
        ),
        _fixture_invoice(
            6, "UNPAID", solo, "2026-07-01", "2026-07-31", [("Workshop", "1", "320.00", "AMOUNT")], "320.00", due_amount="320.00"
        ),
        _fixture_invoice(
            7,
            "PARTIALLY_REFUNDED",
            solo,
            "2026-08-15",
            "2026-09-14",
            [("Workshop", "2", "320.00", "AMOUNT")],
            "640.00",
            paid=("640.00", "2026-08-30", "CASH"),
            refund=("120.00", "2026-09-12"),
        ),
        _fixture_invoice(
            8, "DRAFT", initech, "2026-11-04", "2026-12-04", [("Analyst seat", "5", "49.00", "QUANTITY")], "245.00", due_amount="245.00"
        ),
    ]
    products = [
        {
            "id": "PROD-FIXT-1",
            "name": "Analyst Workspace",
            "type": "SERVICE",
            "category": "SOFTWARE",
            "description": "Seats for the reporting workspace",
        },
        {
            "id": "PROD-FIXT-2",
            "name": "Data Add-ons",
            "type": "DIGITAL",
            "category": "SOFTWARE",
            "description": "Extra connectors and history",
        },
        {
            "id": "PROD-FIXT-3",
            "name": "Field Kit",
            "type": "PHYSICAL",
            "category": "ELECTRONICS_AND_COMPUTERS",
            "description": "Hardware starter kit",
        },
    ]

    def plan(
        n: int,
        product: int,
        name: str,
        unit: str,
        count: int,
        price: str,
        *,
        status: str = "ACTIVE",
        trial_days: int = 0,
        setup: str | None = None,
    ) -> dict:
        cycles = []
        if trial_days:
            cycles.append(
                {
                    "tenure_type": "TRIAL",
                    "sequence": 1,
                    "total_cycles": 1,
                    "frequency": {"interval_unit": "DAY", "interval_count": trial_days},
                }
            )
        cycles.append(
            {
                "tenure_type": "REGULAR",
                "sequence": len(cycles) + 1,
                "total_cycles": 0,
                "frequency": {"interval_unit": unit, "interval_count": count},
                "pricing_scheme": {"fixed_price": _usd(price)},
            }
        )
        return {
            "id": f"P-FIXT-{n}",
            "product_id": f"PROD-FIXT-{product}",
            "name": name,
            "status": status,
            "billing_cycles": cycles,
            "payment_preferences": {"setup_fee": _usd(setup)} if setup else {},
        }

    plans = [
        plan(1, 1, "Workspace Monthly", "MONTH", 1, "49.00", trial_days=14),
        plan(2, 1, "Workspace Annual", "YEAR", 1, "490.00", setup="50.00"),
        plan(3, 2, "Add-ons Quarterly", "MONTH", 3, "60.00"),
        plan(4, 3, "Field Kit Weekly Rental", "WEEK", 1, "15.00", status="INACTIVE"),
    ]
    transactions = [
        _fixture_payout(1, "2026-10-12", "120.00", "1.20", "ravi@affiliates.example", "AFFILIATES", "9880.00"),
        _fixture_payout(2, "2026-10-14", "85.00", "0.85", "mei@affiliates.example", "AFFILIATES", "9794.15"),
        _fixture_payout(3, "2026-10-19", "200.00", "2.00", "noor@creators.example", "CREATORS", "9592.15"),
        _fixture_payout(4, "2026-10-26", "150.00", "1.50", "omar@creators.example", "CREATORS", "9440.65"),
        _fixture_payout(5, "2026-11-02", "60.00", "0.60", "lena@example.com", "REFUNDS", "9380.05"),
        {
            "transaction_info": {
                "transaction_id": "TXN-FIXT-0006",
                "transaction_event_code": "T1105",
                "transaction_initiation_date": "2026-10-30T09:00:00+0000",
                "transaction_amount": _usd("500.00"),
                "fee_amount": _usd("0.00"),
                "transaction_status": "S",
                "ending_balance": _usd("9880.05"),
                "transaction_note": "Hold released",
            },
        },
    ]
    balances = {
        "as_of_time": "2026-11-05T12:00:00Z",
        "balances": [
            {"currency": "USD", "total_balance": _usd("9880.05"), "available_balance": _usd("9380.05"), "withheld_balance": _usd("500.00")}
        ],
    }
    return {"products": products, "plans": plans, "invoices": invoices, "transactions": transactions, "balances": balances}


# ---- endpoint ------------------------------------------------------------------------------------

_cache: dict = {}
_cache_lock = threading.Lock()


def _gateway():
    return make_gateway(settings)


def paypal_tables(gw=None, now: datetime | None = None) -> dict:
    """The related tables plus `source`: "live" when read from the sandbox account, else "replay" (fixture)."""
    gw = gw or _gateway()
    if isinstance(gw, SandboxPayPal):
        as_of = (now or datetime.now(UTC)).replace(microsecond=0)
        return {"source": "live", **build_tables(fetch_account(gw, as_of), as_of)}
    return {"source": "replay", **build_tables(fixture_account(), FIXTURE_AS_OF)}


@router.get("/studio/paypal")
def studio_paypal(fixture: bool = False):
    """Tables behind the Command Center's PayPal overview pages. A plain `def`, so FastAPI runs the blocking
    httpx calls in its thread pool, off the event loop."""
    if fixture:
        return {"source": "replay", **build_tables(fixture_account(), FIXTURE_AS_OF)}
    gw = _gateway()
    if not isinstance(gw, SandboxPayPal):
        return paypal_tables(gw)
    with _cache_lock:  # one live read at a time; reloads within the TTL reuse it
        hit = _cache.get("live")
        if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
            return hit[1]
        try:
            tables = paypal_tables(gw)
        except PayPalAPIError as e:
            raise HTTPException(502, f"PayPal sandbox read failed: {e}") from e
        _cache["live"] = (time.monotonic(), tables)
        return tables
