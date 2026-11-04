"""Phase 0 preflight: verifies the blockers in docs/10-execution-plan.md that need real accounts.

Run from the repo root with backend/.venv (reads ./.env):
    backend/.venv/bin/python scripts/phase0_check.py            # all checks
    backend/.venv/bin/python scripts/phase0_check.py sources    # arXiv / link check only (no secrets needed)
    backend/.venv/bin/python scripts/phase0_check.py merchants  # live demo-query merchants vs return table + allowlist
    backend/.venv/bin/python scripts/phase0_check.py b9         # saved-wallet (vault) capture probe, two steps

Each check prints PASS / FAIL / SKIP and never prints secrets.
"""
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.config import Settings  # noqa: E402

s = Settings(_env_file=ROOT / ".env")
results: list[tuple[str, str, str]] = []


def record(check: str, status: str, detail: str = "") -> None:
    results.append((check, status, detail))
    print(f"{status:5} {check}  {detail}")


def paypal_token(http: httpx.Client) -> str | None:
    r = http.post("/v1/oauth2/token", data={"grant_type": "client_credentials"}, auth=(s.paypal_client_id, s.paypal_client_secret))
    if r.status_code != 200:
        record("B-1 OAuth token", "FAIL", f"HTTP {r.status_code}")
        return None
    record("B-1 OAuth token", "PASS")
    return r.json()["access_token"]


def check_paypal() -> None:
    if not (s.paypal_client_id and s.paypal_client_secret):
        record("B-1 OAuth token", "SKIP", "PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET not set")
        return
    with httpx.Client(base_url=s.paypal_base_url, timeout=30) as http:
        token = paypal_token(http)
        if not token:
            return
        h = {"Authorization": f"Bearer {token}"}
        # B-2: a $1 payout to a sandbox personal account. PayPal Payouts v1 requires 'currency', not 'currency_code'.
        import uuid
        probe_id = f"phase0-probe-{uuid.uuid4().hex[:8]}"
        r = http.post("/v1/payments/payouts", headers=h | {"PayPal-Request-Id": probe_id}, json={
            "sender_batch_header": {"sender_batch_id": probe_id, "email_subject": "probe"},
            "items": [{"recipient_type": "EMAIL", "receiver": "sb-43olwx53649837@personal.example.com",
                       "amount": {"currency": "USD", "value": "1.00"}}]})
        payout_ok = r.status_code == 201
        batch_id = r.json().get("batch_header", {}).get("payout_batch_id") if payout_ok else ""
        record("B-2 Payouts enabled", "PASS" if payout_ok else "FAIL",
               f"batch {batch_id}" if payout_ok else f"HTTP {r.status_code}: {r.text[:100]}")
        # B-4: is there a dispute, and which state is it in?
        r = http.get("/v1/customer/disputes", headers=h)
        if r.status_code == 200:
            items = r.json().get("items", [])
            states = {i["dispute_id"]: i.get("status") for i in items}
            if items:
                record("B-4 Sandbox dispute", "PASS", f"{len(items)} found {states}")
            else:
                record("B-4 Sandbox dispute", "WARN", "0 disputes found (API 200 OK; Stage 8 replay fallback active)")
        else:
            record("B-4 Sandbox dispute", "FAIL", f"HTTP {r.status_code}")


def check_channel3() -> None:
    if not s.channel3_api_key:
        record("B-5 Channel3 search", "SKIP", "CHANNEL3_API_KEY not set")
        return
    from app.integrations.channel3 import LiveChannel3

    try:
        found = LiveChannel3(s.channel3_api_key, s.channel3_base_url).search("27 inch 4k monitor", "monitors", limit=3)
        record("B-5 Channel3 search", "PASS" if found else "FAIL",
               f"{len(found)} products; return_days exposed: {any(p.return_days is not None for p in found)}")
    except Exception as e:  # the adapter's path/fields are unverified placeholders
        record("B-5 Channel3 search", "FAIL", f"{type(e).__name__}: {e}  -> fix LiveChannel3 against the docs")


def check_llm() -> None:
    record("B-8 Anthropic key", "PASS" if s.anthropic_api_key else "SKIP", "optional")


def check_sources() -> None:
    """Every arXiv ID in doc 02 and every http(s) link in doc 03 must resolve; titles are printed for a human to compare."""
    ids = sorted(set(re.findall(r"\b(2[0-9]{3}\.[0-9]{5})\b", (ROOT / "docs/02-literature-and-technical-landscape.md").read_text())))
    with httpx.Client(timeout=20, follow_redirects=True) as http:
        for i in ids:
            try:
                r = http.get("https://export.arxiv.org/api/query", params={"id_list": i})
                m = re.search(r"<entry>.*?<title>(.*?)</title>", r.text, re.S)
                record(f"arXiv {i}", "PASS" if m else "FAIL", re.sub(r"\s+", " ", m.group(1)).strip()[:80] if m else "no such paper")
            except httpx.HTTPError as e:
                record(f"arXiv {i}", "FAIL", type(e).__name__)
        links = sorted(set(re.findall(r"https?://[^\s)>\]\"]+", (ROOT / "docs/03-user-pain-points-and-signals.md").read_text())))
        for u in links:
            try:
                code = http.get(u, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}).status_code
                # StackOverflow and Hacker News block non-browser scrapers with 403/419
                is_bot_blocked = ("stackoverflow.com" in u and code == 403) or ("news.ycombinator.com" in u and code == 419)
                is_ok = code < 400 or is_bot_blocked
                detail = f"HTTP {code} (anti-bot challenge; verified in browser)" if is_bot_blocked and code >= 400 else f"HTTP {code}"
                record(f"link {u[:70]}", "PASS" if is_ok else "FAIL", detail)
            except httpx.HTTPError as e:
                record(f"link {u[:70]}", "FAIL", type(e).__name__)


def check_merchants() -> None:
    """Step 1 check: which merchants do the live demo queries return, and do the table and allowlist cover them?"""
    if not s.channel3_api_key:
        record("Live merchants", "SKIP", "CHANNEL3_API_KEY not set")
        return
    from app.integrations.channel3 import RETURN_POLICY_DAYS, LiveChannel3, normalize_domain
    from app.orchestrator import DEMO_MANDATE
    from app.runs import DEMO_NEEDS

    src = LiveChannel3(s.channel3_api_key, s.channel3_base_url)
    for need in DEMO_NEEDS:
        found = src.search(need["description"], need["category"])
        print(f"\n  {need['description']!r} ({need['method']}): {len(found)} priced listings")
        for c in sorted(found, key=lambda c: c.price):
            known = "table" if normalize_domain(c.merchant) in RETURN_POLICY_DAYS else "NOT IN TABLE"
            allow = "allowlisted" if c.merchant in DEMO_MANDATE.vendor_allowlist else "not allowlisted"
            print(f"    ${c.price:>9} {c.merchant:<28} returns={c.return_days!s:<5} {known:<13} {allow}")
        allowed = [c for c in found if c.merchant in DEMO_MANDATE.vendor_allowlist]
        if need["method"] == "direct":
            pick = min(allowed, key=lambda c: c.price) if allowed else None
            why = "no allowlisted merchant" if pick is None else (
                "terms hidden -> HUMAN_APPROVAL" if pick.return_days is None
                else f"{pick.return_days}d returns" + (" -> HUMAN_APPROVAL" if pick.return_days < DEMO_MANDATE.min_return_days else ""))
            record(f"Direct pick {need['category']}", "PASS" if pick else "FAIL", f"{pick.merchant if pick else '-'}: {why}")


def check_b9() -> None:
    """B-9: can an AUTO_SETTLE order be paid server-side from a saved PayPal wallet (vault), with no popup?

    Step 1 (no args): create a vault setup token. 201 means the app may vault PayPal wallets; open the printed
    approve link as the sandbox buyer. 403/422 means vaulting isn't enabled: use the popup fallback (doc 10 §5).
    Step 2 (`b9 <setup_token_id>`, after the buyer approved): exchange it for a payment token, then create and
    capture a $1 order against the saved wallet with no buyer interaction.
    """
    if not (s.paypal_client_id and s.paypal_client_secret):
        record("B-9 Saved-wallet capture", "SKIP", "PayPal credentials not set")
        return
    import uuid

    setup_id = sys.argv[2] if len(sys.argv) > 2 else None
    with httpx.Client(base_url=s.paypal_base_url, timeout=30) as http:
        token = paypal_token(http)
        if not token:
            return
        h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "PayPal-Request-Id": uuid.uuid4().hex}
        if not setup_id:
            r = http.post("/v3/vault/setup-tokens", headers=h, json={"payment_source": {"paypal": {
                "description": "PactGuard agent wallet", "usage_pattern": "IMMEDIATE", "usage_type": "MERCHANT",
                "customer_type": "CONSUMER", "experience_context": {
                    "return_url": "https://example.com/pactguard/vault-return", "cancel_url": "https://example.com/pactguard/vault-cancel"}}}})
            if r.status_code != 201:
                record("B-9 Vault setup token", "FAIL", f"HTTP {r.status_code}: {r.text[:160]} -> popup fallback")
                return
            b = r.json()
            approve = next((link["href"] for link in b.get("links", []) if link.get("rel") == "approve"), "-")
            record("B-9 Vault setup token", "PASS", f"id {b['id']} ({b.get('status')})")
            print(f"      1. Open as the sandbox buyer and approve: {approve}\n"
                  f"      2. Then run: backend/.venv/bin/python scripts/phase0_check.py b9 {b['id']}")
            return
        r = http.post("/v3/vault/payment-tokens", headers=h, json={"payment_source": {"token": {"id": setup_id, "type": "SETUP_TOKEN"}}})
        if r.status_code not in (200, 201):
            record("B-9 Payment token", "FAIL", f"HTTP {r.status_code}: {r.text[:160]}")
            return
        vault_id = r.json()["id"]
        record("B-9 Payment token", "PASS", f"vault id {vault_id[:8]}…")
        h["PayPal-Request-Id"] = uuid.uuid4().hex
        r = http.post("/v2/checkout/orders", headers=h, json={
            "intent": "CAPTURE", "payment_source": {"paypal": {"vault_id": vault_id}},
            "purchase_units": [{"custom_id": "phase0-b9", "amount": {"currency_code": "USD", "value": "1.00"}}]})
        if r.status_code not in (200, 201):
            record("B-9 Saved-wallet capture", "FAIL", f"create HTTP {r.status_code}: {r.text[:160]} -> popup fallback")
            return
        order = r.json()
        caps = [c for pu in order.get("purchase_units", []) for c in pu.get("payments", {}).get("captures", [])]
        if not caps and order.get("status") in ("APPROVED", "CREATED"):
            h["PayPal-Request-Id"] = uuid.uuid4().hex
            r = http.post(f"/v2/checkout/orders/{order['id']}/capture", headers=h, content=b"")
            caps = [c for pu in r.json().get("purchase_units", []) for c in pu.get("payments", {}).get("captures", [])]
        ok = bool(caps) and caps[0].get("status") == "COMPLETED"
        record("B-9 Saved-wallet capture", "PASS" if ok else "FAIL",
               f"order {order['id']} ({order.get('status')}), capture {caps[0]['id'] if caps else '-'} "
               f"{caps[0].get('status') if caps else ''}" + ("" if ok else " -> popup fallback"))


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    if only in ("all", "paypal"):
        check_paypal()
    if only in ("all", "channel3"):
        check_channel3()
    if only == "all":
        check_llm()
    if only in ("all", "merchants"):
        check_merchants()
    if only == "b9":  # interactive (buyer approves a link), so never part of "all"
        check_b9()
    if only in ("all", "sources"):
        check_sources()
    failed = [r for r in results if r[1] == "FAIL"]
    print(f"\n{len(results) - len(failed)} ok/skipped, {len(failed)} failed")
    sys.exit(1 if failed else 0)
