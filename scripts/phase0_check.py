"""Phase 0 preflight: verifies the blockers in docs/10-execution-plan.md that need real accounts.

Run from the repo root with backend/.venv (reads ./.env):
    backend/.venv/bin/python scripts/phase0_check.py            # all checks
    backend/.venv/bin/python scripts/phase0_check.py sources    # arXiv / link check only (no secrets needed)

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
        # B-2: a $1 payout to a sandbox personal account. 403 means Payouts is not enabled on the business account.
        r = http.post("/v1/payments/payouts", headers=h | {"PayPal-Request-Id": "phase0-payout-probe-1"}, json={
            "sender_batch_header": {"sender_batch_id": "phase0-probe-1", "email_subject": "probe"},
            "items": [{"recipient_type": "EMAIL", "receiver": "sb-buyer@personal.example.com",
                       "amount": {"currency_code": "USD", "value": "1.00"}}]})
        record("B-2 Payouts enabled", "PASS" if r.status_code == 201 else "FAIL",
               f"HTTP {r.status_code} (set receiver to your sandbox buyer email; 403 = Payouts not enabled)")
        # B-4: is there a dispute, and which state is it in?
        r = http.get("/v1/customer/disputes", headers=h)
        if r.status_code == 200:
            items = r.json().get("items", [])
            states = {i["dispute_id"]: i.get("status") for i in items}
            record("B-4 Sandbox dispute", "PASS" if items else "FAIL", f"{len(items)} found {states}")
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
                code = http.get(u, headers={"User-Agent": "phase0-check"}).status_code
                record(f"link {u[:70]}", "PASS" if code < 400 else "FAIL", f"HTTP {code}")
            except httpx.HTTPError as e:
                record(f"link {u[:70]}", "FAIL", type(e).__name__)


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    if only in ("all", "paypal"):
        check_paypal()
    if only in ("all", "channel3"):
        check_channel3()
    if only == "all":
        check_llm()
    if only in ("all", "sources"):
        check_sources()
    failed = [r for r in results if r[1] == "FAIL"]
    print(f"\n{len(results) - len(failed)} ok/skipped, {len(failed)} failed")
    sys.exit(1 if failed else 0)
