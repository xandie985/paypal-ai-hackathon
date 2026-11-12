"""Lineage drawer and mandate before/after: both read the sealed ledger and never write to it."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def run_id():
    return client.post("/api/runs").json()["run_id"]


def test_studio_lineage_returns_chained_entries_for_a_run_and_for_seeded_history(run_id):
    rows = client.get("/api/studio/rows", params={"run_id": run_id, "history": True}).json()["rows"]
    for source in ("run", "seeded"):
        row = next(r for r in rows if r["source"] == source and r.get("status") == "CAPTURED")
        out = client.get(f"/api/studio/lineage/{row['lineage_id']}").json()
        assert out["source"] == source and out["chain_ok"] is True
        kinds = [e["kind"] for e in out["entries"]]
        assert "decision" in kinds and "seal" in kinds and "capture" in kinds
        assert all(e["entry_hash"] and e["prev_hash"] for e in out["entries"])


def test_unknown_lineage_is_404():
    assert client.get("/api/studio/lineage/PG-nope.0000000000").status_code == 404


def test_run_calibration_preview_writes_nothing(run_id):
    before = client.get(f"/api/runs/{run_id}").json()["ledger_entries"]
    out = client.get(f"/api/runs/{run_id}/calibration").json()
    assert out["changed"] is False and out["diff"] == []  # two clean purchases: nothing to learn yet
    assert client.get(f"/api/runs/{run_id}").json()["ledger_entries"] == before


def test_seeded_history_has_mandate_diffs_linked_by_parent_digest():
    cals = client.get("/api/studio/calibrations").json()["calibrations"]
    assert cals, "seeded history should include at least one calibrated mandate"
    c = cals[0]
    assert c["parent_digest_linked"] is True and c["changes"] and c["diff"]
    assert c["after"]["version"] == c["before"]["version"] + 1
    fields = {d["field"] for d in c["diff"]}
    assert fields & {"auto_threshold", "vendor_allowlist"}


def test_ledger_checkpoint_and_verify_endpoint():
    # Fetch signed head checkpoint
    cp = client.get("/api/ledger/checkpoint").json()
    assert "seq" in cp and "head_hash" in cp and "signature" in cp
    # Verify with matching checkpoint params
    v = client.get(
        "/api/ledger/verify",
        params={"checkpoint_seq": cp["seq"], "checkpoint_hash": cp["head_hash"], "signature": cp["signature"]},
    ).json()
    assert v["chain_ok"] is True and v["first_bad_seq"] is None
