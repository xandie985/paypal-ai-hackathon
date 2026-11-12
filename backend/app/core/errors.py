"""Guard violations. Each maps to a row of the hand-off failure table in
docs/09-implementation-framework.md, so a failing guard names the hand-off it protects."""


class GuardViolation(Exception):
    code = "GUARD_VIOLATION"
    handoff = ""

    def __init__(self, message: str, **context):
        super().__init__(message)
        self.context = context

    def to_dict(self) -> dict:
        return {"code": self.code, "handoff": self.handoff, "message": str(self), **self.context}


class DoubleCommitment(GuardViolation):
    code, handoff = "DOUBLE_COMMITMENT", "2->3"


class SchemaGateRejected(GuardViolation):
    code, handoff = "SCHEMA_GATE_REJECTED", "2->3"


class AmountMismatch(GuardViolation):
    code, handoff = "AMOUNT_MISMATCH", "3->4"


class BudgetExceeded(GuardViolation):
    code, handoff = "BUDGET_EXCEEDED", "3->4"


class NotAuthorized(GuardViolation):
    code, handoff = "NOT_AUTHORIZED", "3->4"


class SealWriteFailed(GuardViolation):
    code, handoff = "SEAL_WRITE_FAILED", "4->5"


class SealMissing(GuardViolation):
    code, handoff = "SEAL_MISSING", "4->5"


class NotCaptured(GuardViolation):
    code, handoff = "NOT_CAPTURED", "4"


class InvoiceNotDraft(GuardViolation):
    code, handoff = "INVOICE_NOT_DRAFT", "4"


class GateTokenInvalid(GuardViolation):
    code, handoff = "GATE_TOKEN_INVALID", "5->7"


class InvoiceFlagged(GuardViolation):
    code, handoff = "INVOICE_FLAGGED", "6->7"


class WebhookUnverified(GuardViolation):
    code, handoff = "WEBHOOK_UNVERIFIED", "7->8"


class DisputeAlreadyAnswered(GuardViolation):
    code, handoff = "DISPUTE_ALREADY_ANSWERED", "8"


class DisputeActionUnavailable(GuardViolation):
    code, handoff = "DISPUTE_ACTION_UNAVAILABLE", "8"
