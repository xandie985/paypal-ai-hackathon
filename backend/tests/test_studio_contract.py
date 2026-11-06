"""The Studio row contract and the seeded history behind it.

Widgets bind to row keys by name, so a renamed column silently empties a saved dashboard. These
tests freeze the keys, check the frontend's field ids against them, and check that seeded history
really comes from the firewall and settlement code rather than hand-written rows."""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.seed import build_history
from app.stages.s09_observe import ROW_COLUMNS, transaction_rows

client = TestClient(app)
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
COMMAND_CENTER = Path(__file__).parents[2] / "frontend" / "src" / "studio" / "CommandCenter.tsx"

# Changing this list is a breaking change for saved Studio dashboards: update the frontend fields and
# say so in the PR. Adding a column is fine; renaming or removing one is not.
FROZEN = (
    "lineage_id", "source", "created_at", "updated_at", "vendor", "category", "action", "route", "amount", "savings",
    "firewall_ms", "blocked_reasons", "approved_by", "order_id", "capture_id", "status", "delivery", "invoice_status",
    "payout_net", "dispute_win_odds", "dispute_outcome", "supplier_trust",
)  # fmt: skip


def test_studio_row_columns_are_stable():
    assert ROW_COLUMNS == FROZEN


def test_every_row_key_is_in_the_contract():
    client.post("/api/runs")
    rows = client.get("/api/studio/rows", params={"history": "true"}).json()["rows"]
    keys = {k for r in rows for k in r}
    assert keys <= set(ROW_COLUMNS), keys - set(ROW_COLUMNS)
    assert {"run", "seeded"} <= {r["source"] for r in rows}


def test_frontend_studio_fields_match_the_contract():
    src = COMMAND_CENTER.read_text()
    helpers = set(re.findall(r"^\s*(?:text|money|datetime|percent)\('([a-z_]+)'", src, re.M))
    literals = set(re.findall(r"\{ id: '([a-z_]+)', name: '[^']*', description: '[^']*', format:", src))
    field_ids = helpers | literals
    table_cols = set(re.findall(r"'([a-z_]+)'", re.search(r"cols: \[([^\]]*)\]", src).group(1)))
    money = set(re.findall(r"'([a-z_]+)'", re.search(r"const MONEY = \[([^\]]*)\]", src).group(1)))
    assert field_ids and field_ids <= set(ROW_COLUMNS), field_ids - set(ROW_COLUMNS)
    assert table_cols <= field_ids, table_cols - field_ids  # the table can only show defined fields
    widget_refs = set(re.findall(r"f\('([a-z_]+)'\)", src)) | set(re.findall(r"only\('([a-z_]+)'", src))
    assert {"vendor", "route", "dispute_outcome", "supplier_trust", "savings"} <= widget_refs
    assert widget_refs <= field_ids, widget_refs - field_ids  # every widget, filter and sort binds a defined field
    assert money <= field_ids


def test_seeded_history_comes_from_the_real_code_path():
    led = build_history(now=NOW)
    assert led.verify() == (True, None)
    rows = transaction_rows(led)
    assert len(rows) >= 40
    routes = {r["route"] for r in rows}
    assert routes == {"AUTO_SETTLE", "HUMAN_APPROVAL", "BLOCKED"}
    for r in rows:
        lid = r["lineage_id"]
        decision = led.latest(lid, "decision")
        assert decision, f"{lid}: no firewall decision"  # every row went through s03_govern.evaluate
        if r.get("status") == "CAPTURED":
            kinds = [e.kind for e in led.entries(lid)]
            assert kinds.index("seal") < kinds.index("capture")  # seal before money, as in a live run
            if decision.payload["route"] == "HUMAN_APPROVAL":
                assert "approval" in kinds  # nothing settled past the approval gate without one
        if decision.payload["route"] == "BLOCKED":
            assert not led.latest(lid, "capture")
    assert any(r.get("dispute_outcome") for r in rows) and any(r.get("status") == "REJECTED" for r in rows)
    assert any(e.payload["proposal"]["action"] == "payout" for e in led.entries(kind="decision"))  # injected attacks


def test_seeded_history_is_spread_over_past_days_and_deterministic():
    a, b = build_history(now=NOW), build_history(now=NOW)
    ra, rb = transaction_rows(a), transaction_rows(b)
    stamps = [datetime.fromisoformat(r["created_at"]) for r in ra]
    assert max(stamps) < NOW and min(stamps) >= NOW - timedelta(days=30)
    assert (max(stamps) - min(stamps)).days >= 20
    strip = lambda rows: [(r["vendor"], r["route"], r["amount"], r.get("status")) for r in rows]  # noqa: E731
    assert strip(ra) == strip(rb)


def test_history_is_opt_in_and_verifiable():
    snap = client.post("/api/runs").json()
    plain = client.get("/api/studio/rows", params={"run_id": snap["run_id"]}).json()["rows"]
    assert {r["source"] for r in plain} == {"run"}
    both = client.get("/api/studio/rows", params={"run_id": snap["run_id"], "history": "true"}).json()["rows"]
    assert len(both) > len(plain) and both[0]["source"] == "run"  # the current run is newest, so on top
    v = client.get("/api/studio/history/verify").json()
    assert v["chain_ok"] is True and v["entries"] > 100


def test_supplier_trust_matches_stage_10():
    """The column and stage 10 must agree, or the dashboard and the mandate calibration tell different stories."""
    from app.stages.s09_observe import with_supplier_trust
    from app.stages.s10_learn import supplier_trust

    led = build_history(now=NOW)
    rows = with_supplier_trust(transaction_rows(led))
    by_vendor = {r["vendor"]: r["supplier_trust"] for r in rows if "supplier_trust" in r}
    attacks = [r for r in rows if r.get("action") == "payout"]
    assert attacks and all("supplier_trust" not in r for r in attacks)  # an injected payout has no supplier to score
    for vendor, score in supplier_trust(led, None).items():
        assert by_vendor[vendor] == score, vendor
    assert all(0 < t <= 1 for t in by_vendor.values())
