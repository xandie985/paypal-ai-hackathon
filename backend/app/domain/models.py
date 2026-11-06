"""Contracts passed between stages. Anything an agent or seller produces is parsed
into one of these before it can move the loop forward (schema gate)."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..core.canonical import sha256_hex


class Mandate(BaseModel):
    """Stage 1. The control knob: stage 10 emits new versions of this."""

    model_config = ConfigDict(frozen=True)

    principal: str
    purpose: str
    currency: str = "USD"
    budget: Decimal
    auto_threshold: Decimal = Field(description="Max total that may settle without a human")
    per_txn_cap: Decimal
    vendor_allowlist: list[str]
    allowed_categories: list[str]
    min_return_days: int = 30
    max_price_premium_pct: Decimal = Decimal("10")  # vs discovery baseline
    mode: Literal["auto", "review_first"] = "auto"
    version: int = 1
    parent_digest: str | None = None

    def digest(self) -> str:
        return sha256_hex(self.model_dump(mode="json"))


class Need(BaseModel):
    description: str
    category: str
    quantity: int = Field(ge=1)
    max_unit_price: Decimal | None = None


class ProductCandidate(BaseModel):
    product_id: str
    title: str
    merchant: str
    category: str
    price: Decimal
    currency: str = "USD"
    return_days: int | None = None  # None = merchant hides return terms (blocker B2a)
    url: str = ""
    image_url: str = ""
    source: str = "replay"


class Offer(BaseModel):
    """One seller turn. extra='forbid' rejects anything the schema doesn't name."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    seller_id: str
    sku: str
    turn: int = Field(ge=1, le=3)
    action: Literal["quote", "counter", "final"]
    unit_price: Decimal = Field(gt=0)
    quantity: int = Field(ge=1)
    return_days: int = Field(ge=0)
    ship_days: int = Field(ge=0)
    terms: str = Field(default="", max_length=500)


class Proposal(BaseModel):
    """What the firewall evaluates: any money movement an agent wants to make."""

    lineage_id: str
    action: Literal["order", "payout"] = "order"
    origin: Literal["negotiation", "discovery", "agent_tool_call"] = "negotiation"
    vendor: str
    category: str
    sku: str
    unit_price: Decimal
    quantity: int
    return_days: int | None
    baseline_unit_price: Decimal | None = None
    untrusted_text: list[str] = []
    payee: str | None = None

    @property
    def total(self) -> Decimal:
        return self.unit_price * self.quantity


Route = Literal["AUTO_SETTLE", "HUMAN_APPROVAL", "BLOCKED"]


class FactorResult(BaseModel):
    name: str
    passed: bool
    hard: bool  # a hard failure blocks; a soft one routes to a human
    detail: str


class Decision(BaseModel):
    lineage_id: str
    route: Route
    factors: list[FactorResult]
    reasons: list[str]
    decision_digest: str
    request_id: str
    latency_ms: float


class DeliveryReport(BaseModel):
    carrier: str = ""
    tracking_number: str = ""
    tracking_status: Literal["DELIVERED", "IN_TRANSIT", "LOST", "NONE"] = "NONE"
    delivered_on: str | None = None
    due_by: str
    rubric: dict[str, bool] = {}  # acceptance criteria for services / deliverables


class VendorInvoice(BaseModel):
    vendor: str
    invoice_number: str
    amount: Decimal
    payee_email: str
    lineage_id: str
    memo: str = ""


class Dispute(BaseModel):
    dispute_id: str
    lineage_id: str
    reason: str  # PayPal's reason code; live disputes use more codes than the three REQUIRED maps
    amount: Decimal
    seller_response_due_date: str
