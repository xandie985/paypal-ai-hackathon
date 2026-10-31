"""Stage 5 - DELIVER and VERIFY. Checks delivery against the sealed terms and an
acceptance rubric, writes the proof to the ledger, and only on PASS mints the
VERIFIED gate token that stage 7 needs to pay out."""

from datetime import date, timedelta

from ..core.gates import VERIFIED, issue
from ..core.ledger import EvidenceLedger
from ..domain.models import DeliveryReport

STAGE = "5-verify"


def verify_delivery(ledger: EvidenceLedger, secret: str, lineage_id: str, order_id: str, report: DeliveryReport) -> dict:
    problems = []
    if report.tracking_status != "DELIVERED":
        problems.append(f"tracking status {report.tracking_status}")
    late = bool(report.delivered_on and date.fromisoformat(report.delivered_on) > date.fromisoformat(report.due_by))
    if late:
        problems.append(f"delivered {report.delivered_on} after due {report.due_by}")
    failed = [k for k, ok in report.rubric.items() if not ok]
    if failed:
        problems.append("rubric failed: " + ", ".join(failed))

    verdict = "PASS" if not problems else ("LATE" if late and len(problems) == 1 else "FAIL")
    ledger.append(
        lineage_id,
        STAGE,
        "delivery_proof",
        {"order_id": order_id, "verdict": verdict, "problems": problems, **report.model_dump(mode="json")},
    )
    token = issue(secret, VERIFIED, lineage_id, order_id) if verdict == "PASS" else None
    return {"verdict": verdict, "problems": problems, "token": token}


def reschedule(tranches: list[dict], slip_days: int) -> list[dict]:
    """Gantt-lite: payment tranches are dependent tasks; a slip pushes every
    unreleased tranche by the same number of days. (Full Bryntum Gantt is cut.)"""
    out = []
    for t in tranches:
        due = date.fromisoformat(t["due"])
        out.append({**t, "due": (due + timedelta(days=slip_days)).isoformat() if not t.get("released") else t["due"]})
    return out
