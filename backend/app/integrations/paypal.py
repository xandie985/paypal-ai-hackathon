"""PayPal gateway. Two interchangeable implementations behind one interface:

- ReplayPayPal: deterministic in-memory sandbox double. Honors PayPal-Request-Id
  idempotency the way the real API does, and can inject the failures the guards
  defend against (pending capture, invoice created live, unverifiable webhooks).
- SandboxPayPal: real REST calls (Orders v2, Invoicing v2, Payouts v1, Disputes v1,
  webhook verification) with a cached OAuth token.

The PayPal agent toolkit has no spend cap, no Payouts tool and only
accept_dispute_claim for disputes, so stages call this gateway directly and the
toolkit is optional for read-only tools.
"""

import itertools
import json
import time
from typing import Protocol

import httpx


class PayPalGateway(Protocol):
    def create_order(self, purchase_unit: dict, request_id: str) -> dict: ...
    def capture_order(self, order_id: str, request_id: str) -> dict: ...
    def create_invoice(self, invoice: dict, request_id: str) -> dict: ...
    def send_invoice(self, invoice_id: str, request_id: str) -> dict: ...
    def remind_invoice(self, invoice_id: str, request_id: str) -> dict: ...
    def create_payout(self, batch: dict, request_id: str) -> dict: ...
    def provide_evidence(self, dispute_id: str, evidence: dict, files: list[tuple[str, bytes]]) -> dict: ...
    def verify_webhook(self, headers: dict, body: dict) -> bool: ...


class ReplayPayPal:
    def __init__(self, capture_status: str = "COMPLETED", invoice_initial_status: str = "DRAFT", webhooks_valid=True):
        self.capture_status = capture_status
        self.invoice_initial_status = invoice_initial_status
        self.webhooks_valid = webhooks_valid
        self._by_request: dict[str, dict] = {}
        self._ids = itertools.count(1)
        self.calls: list[tuple[str, str]] = []  # (operation, request_id): lets tests count real side effects
        self.orders: dict[str, dict] = {}
        self.evidence: dict[str, dict] = {}

    def _idempotent(self, op: str, request_id: str, make) -> dict:
        if request_id in self._by_request:
            return self._by_request[request_id]
        self.calls.append((op, request_id))
        self._by_request[request_id] = make()
        return self._by_request[request_id]

    def _id(self, prefix: str) -> str:
        return f"{prefix}{next(self._ids):06d}"

    def create_order(self, purchase_unit, request_id):
        def make():
            oid = self._id("ORD-REPLAY-")
            # Replay auto-approves; in sandbox the buyer approves via the JS SDK first.
            self.orders[oid] = {"id": oid, "status": "APPROVED", "purchase_units": [purchase_unit]}
            return self.orders[oid]

        return self._idempotent("create_order", request_id, make)

    def capture_order(self, order_id, request_id):
        def make():
            amount = self.orders[order_id]["purchase_units"][0]["amount"]
            cap = {"id": self._id("CAP-"), "status": self.capture_status, "amount": {k: amount[k] for k in ("currency_code", "value")}}
            self.orders[order_id]["status"] = "COMPLETED"
            return {"id": order_id, "status": "COMPLETED", "purchase_units": [{"payments": {"captures": [cap]}}]}

        return self._idempotent("capture_order", request_id, make)

    def create_invoice(self, invoice, request_id):
        return self._idempotent(
            "create_invoice", request_id, lambda: {"id": self._id("INV2-"), "status": self.invoice_initial_status, **invoice}
        )

    def send_invoice(self, invoice_id, request_id):
        return self._idempotent("send_invoice", request_id, lambda: {"id": invoice_id, "status": "SENT"})

    def remind_invoice(self, invoice_id, request_id):
        return self._idempotent("remind_invoice", request_id, lambda: {"id": invoice_id, "reminded": True})

    def create_payout(self, batch, request_id):
        sbid = batch["sender_batch_header"]["sender_batch_id"]
        return self._idempotent(
            "create_payout",
            request_id,
            lambda: {"batch_header": {"payout_batch_id": self._id("PB-"), "sender_batch_id": sbid, "batch_status": "PENDING"}},
        )

    def provide_evidence(self, dispute_id, evidence, files):
        self.calls.append(("provide_evidence", dispute_id))
        self.evidence[dispute_id] = {"evidence": evidence, "files": [n for n, _ in files]}
        return {"links": [{"rel": "self", "href": f"/v1/customer/disputes/{dispute_id}"}]}

    def verify_webhook(self, headers, body):
        return self.webhooks_valid and "paypal-transmission-sig" in {k.lower() for k in headers}


class SandboxPayPal:
    def __init__(self, client_id: str, client_secret: str, base_url: str, webhook_id: str = ""):
        self._auth = (client_id, client_secret)
        self._webhook_id = webhook_id
        self._http = httpx.Client(base_url=base_url, timeout=30)
        self._token: tuple[str, float] | None = None

    def _bearer(self) -> str:
        if not self._token or self._token[1] < time.time() + 60:
            r = self._http.post("/v1/oauth2/token", data={"grant_type": "client_credentials"}, auth=self._auth)
            r.raise_for_status()
            body = r.json()
            self._token = (body["access_token"], time.time() + body["expires_in"])
        return self._token[0]

    def _post(self, path: str, json_body: dict | None, request_id: str | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self._bearer()}", "Prefer": "return=representation"}
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        r = self._http.post(path, json=json_body, headers=headers)
        r.raise_for_status()
        return r.json() if r.content else {}

    def create_order(self, purchase_unit, request_id):
        return self._post("/v2/checkout/orders", {"intent": "CAPTURE", "purchase_units": [purchase_unit]}, request_id)

    def capture_order(self, order_id, request_id):
        return self._post(f"/v2/checkout/orders/{order_id}/capture", None, request_id)

    def create_invoice(self, invoice, request_id):
        return self._post("/v2/invoicing/invoices", invoice, request_id)

    def send_invoice(self, invoice_id, request_id):
        return self._post(f"/v2/invoicing/invoices/{invoice_id}/send", {"send_to_invoicer": True}, request_id)

    def remind_invoice(self, invoice_id, request_id):
        return self._post(f"/v2/invoicing/invoices/{invoice_id}/remind", {}, request_id)

    def create_payout(self, batch, request_id):
        return self._post("/v1/payments/payouts", batch, request_id)

    def provide_evidence(self, dispute_id, evidence, files):
        # Multipart: an `input` JSON part plus evidence files (PDF/JPG/PNG, size-limited by PayPal).
        r = self._http.post(
            f"/v1/customer/disputes/{dispute_id}/provide-evidence",
            headers={"Authorization": f"Bearer {self._bearer()}"},
            files=[("input", (None, json.dumps(evidence), "application/json"))]
            + [("file1" if i == 0 else f"file{i + 1}", (name, data, "application/pdf")) for i, (name, data) in enumerate(files)],
        )
        r.raise_for_status()
        return r.json() if r.content else {}

    def verify_webhook(self, headers, body):
        h = {k.lower(): v for k, v in headers.items()}
        payload = {
            "auth_algo": h.get("paypal-auth-algo"),
            "cert_url": h.get("paypal-cert-url"),
            "transmission_id": h.get("paypal-transmission-id"),
            "transmission_sig": h.get("paypal-transmission-sig"),
            "transmission_time": h.get("paypal-transmission-time"),
            "webhook_id": self._webhook_id,
            "webhook_event": body,
        }
        return self._post("/v1/notifications/verify-webhook-signature", payload).get("verification_status") == "SUCCESS"


def make_gateway(settings) -> PayPalGateway:
    if settings.paypal_live:
        return SandboxPayPal(settings.paypal_client_id, settings.paypal_client_secret, settings.paypal_base_url, settings.paypal_webhook_id)
    return ReplayPayPal()
