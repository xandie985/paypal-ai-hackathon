"""Agent-to-PayPal reconciliation: statuses per capture, orphans, and the endpoint over the replay fixture."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.studio_reconcile import reconcile, summarise

AS_OF = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def agent(cap, amount, *, source="run", age=timedelta(days=2), status="CAPTURED"):
    return {
        "lineage_id": f"PG-{cap}",
        "capture_id": cap,
        "amount": amount,
        "status": status,
        "source": source,
        "vendor": "v",
        "category": "c",
        "created_at": (AS_OF - age).isoformat(),
    }


def txn(tid, amount="-10.00", fee="-0.50", event="Purchase capture", currency="USD"):
    a, f = float(amount), float(fee)
    return {
        "id": tid,
        "amount": a,
        "fee": f,
        "net": round(a + f, 2),
        "eventType": event,
        "direction": "Debit" if a < 0 else "Credit",
        "currency": currency,
        "date": AS_OF.isoformat(),
        "counterparty": "x@y",
    }


def status_of(rows, cap):
    return next(r["status"] for r in rows if r["id"] == cap)


def test_every_status():
    agents = [
        agent("C-OK", "10.00"),
        agent("C-BAD", "10.00"),
        agent("C-EUR", "10.00"),
        agent("C-SIM", "10.00", source="seeded"),
        agent("C-NEW", "10.00", age=timedelta(minutes=30)),
        agent("C-OLD", "10.00", age=timedelta(days=40)),
        agent("C-GONE", "10.00"),
        agent("C-REJ", "10.00", status="REJECTED"),
    ]
    txns = [txn("C-OK"), txn("C-BAD", "-12.00"), txn("C-EUR", currency="EUR"), txn("C-SIM"), txn("ORPHAN"), txn("T-PAYOUT", event="Payout")]
    rows = reconcile(agents, txns, "live", AS_OF)
    assert status_of(rows, "C-OK") == "Matched"
    assert status_of(rows, "C-BAD") == "Amount mismatch"
    assert status_of(rows, "C-EUR") == "Amount mismatch"  # agent purchases are USD; a EUR capture is not the same money
    assert status_of(rows, "C-SIM") == "Matched"  # a seeded row that PayPal does show is still a match
    assert status_of(rows, "C-NEW") == "Pending"
    assert status_of(rows, "C-OLD") == "Outside window"
    assert status_of(rows, "C-GONE") == "Unsettled"
    assert status_of(rows, "ORPHAN") == "Not decided by agent"
    ids = {r["id"] for r in rows}
    assert "C-REJ" not in ids and "T-PAYOUT" not in ids  # not captured / not a purchase capture


def test_simulated_rows_are_not_unsettled():
    rows = reconcile([agent("C-SIM", "10.00", source="seeded"), agent("C-DEMO", "10.00", source="demo")], [], "live", AS_OF)
    assert status_of(rows, "C-SIM") == "Simulated" and status_of(rows, "C-DEMO") == "Unsettled"
    rows = reconcile([agent("C-DEMO", "10.00", source="demo")], [], "replay", AS_OF)
    assert status_of(rows, "C-DEMO") == "Simulated"  # replay never touches PayPal


def test_summary_counts_and_money():
    rows = reconcile([agent("C-OK", "10.00"), agent("C-GONE", "5.00")], [txn("C-OK"), txn("ORPHAN", "-4.00", "-0.20")], "live", AS_OF)
    s = summarise(rows)
    assert (s["captures"], s["matched"], s["unsettled"], s["notDecidedByAgent"]) == (2, 1, 1, 1)
    assert s["fees"] == 0.70 and s["netCash"] == -14.70


def test_endpoint_over_the_replay_fixture():
    client = TestClient(app)
    body = client.get("/api/studio/reconciliation").json()
    assert body["source"] == "replay" and body["asOf"] == "2026-11-05T12:00:00Z"
    matched = {r["id"] for r in body["rows"] if r["status"] == "Matched"}
    assert matched == {"CAP-000064", "CAP-000062", "CAP-000060"}  # the seeded captures the fixture settles
    assert not any(r["status"] in ("Unsettled", "Pending", "Outside window") for r in body["rows"])  # replay: simulated or matched
    assert body["summary"]["simulated"] > 0 and body["summary"]["mismatched"] == 0
    orphans = [r for r in body["rows"] if r["status"] == "Not decided by agent"]
    assert [r["id"] for r in orphans] == ["TXN-FIXT-0007"] and orphans[0]["lineageId"] is None
    assert body == client.get("/api/studio/reconciliation").json()
    assert client.get("/api/studio/reconciliation?fixture=true").json()["rows"] == body["rows"]
