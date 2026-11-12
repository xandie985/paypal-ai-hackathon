"""Check our Orders v2 create-order payloads against APIMatic's generated PayPal Server SDK (`paypal-server-sdk`).

Two steps, because the SDK is not a project dependency and should not be installed into the app's environment:

  1. In the project venv:   PYTHONPATH=backend python backend/scripts/apimatic_check.py generate payloads.json
  2. In a scratch venv with `pip install paypal-server-sdk`:   python backend/scripts/apimatic_check.py validate payloads.json

`generate` runs a replay run and writes the purchase units the app really builds (plus the saved-wallet payment
source shape). `validate` deserialises each into the SDK's `OrderRequest` model, serialises it back and diffs: a key
we send that the model does not know, or a value it changes, is reported. Required fields are the constructor
parameters with no "omitted" sentinel default. A misspelt field is injected as a negative control. The SDK covers
Orders, Payments, Vault, Subscriptions and Transaction Search only: it has no Invoicing, Payouts or Disputes models,
so those payloads are not checked here.
"""

import inspect
import json
import sys


def generate(path: str) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    snap = client.post("/api/runs").json()
    base = f"/api/runs/{snap['run_id']}"
    monitors = next(i for i in snap["items"] if i["need"]["category"] == "monitors")
    client.post(f"{base}/decisions/{monitors['lineage_id']}/approve")
    client.post(f"{base}/orders/{monitors['lineage_id']}/prepare")
    units = [i["purchase_unit"] for i in client.get(base).json()["items"] if i.get("purchase_unit")]
    json.dump({"purchase_units": units, "payment_source": {"paypal": {"vault_id": "VAULT-ID-EXAMPLE"}}}, open(path, "w"), indent=1)
    print(f"wrote {len(units)} purchase units to {path}")


def validate(path: str) -> int:
    from paypalserversdk.api_helper import APIHelper
    from paypalserversdk.models.order_request import OrderRequest
    from paypalserversdk.models.purchase_unit_request import PurchaseUnitRequest

    data = json.load(open(path))

    def required(cls):
        return [p for p, v in inspect.signature(cls.__init__).parameters.items() if p != "self" and v.default is None]

    def diff(ours, back, at=""):
        if isinstance(ours, dict):
            if not isinstance(back, dict):
                return [f"{at}: the model dropped the object"]
            return [
                m
                for k, v in ours.items()
                for m in ([f"{at}.{k}: not in the SDK model (unknown or misnamed)"] if k not in back else diff(v, back[k], f"{at}.{k}"))
            ]
        if isinstance(ours, list):
            if not isinstance(back, list) or len(back) != len(ours):
                return [f"{at}: list changed"]
            return [m for i, (a, b) in enumerate(zip(ours, back, strict=True)) for m in diff(a, b, f"{at}[{i}]")]
        return [] if str(ours) == str(back) else [f"{at}: {ours!r} became {back!r}"]

    def check(body):
        model = OrderRequest.from_dictionary(body)
        problems = diff(body, APIHelper.to_dictionary(model))
        problems += [f"missing required {r}" for r in required(OrderRequest) if getattr(model, r, None) is None]
        problems += [
            f"missing required purchase unit {r}"
            for r in required(PurchaseUnitRequest)
            if getattr(model.purchase_units[0], r, None) is None
        ]
        return problems

    total = 0
    for n, unit in enumerate(data["purchase_units"]):
        found = check({"intent": "CAPTURE", "purchase_units": [unit]})
        print(f"purchase unit {n}: {'OK' if not found else found}")
        total += len(found)
    found = check({"intent": "CAPTURE", "purchase_units": [data["purchase_units"][0]], "payment_source": data["payment_source"]})
    print(f"saved-wallet order: {'OK' if not found else found}")
    total += len(found)
    control = check({"intent": "CAPTURE", "purchase_units": [{**data["purchase_units"][0], "custom_idd": "x"}]})
    print(f"negative control (misspelt field) caught: {bool(control)}")
    if not control:
        total += 1
    print(f"problems: {total}")
    return 1 if total else 0


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("generate", "validate"):
        sys.exit(__doc__)
    if sys.argv[1] == "generate":
        generate(sys.argv[2])
    else:
        sys.exit(validate(sys.argv[2]))
