import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import runs
from .config import settings
from .core.errors import GuardViolation
from .domain.models import Mandate
from .integrations.paypal import PayPalAPIError
from .orchestrator import Runtime, run_demo
from .stages.s09_observe import kpis, transaction_rows

router = APIRouter(prefix="/api")
_rt: Runtime | None = None


def runtime() -> Runtime:
    global _rt
    if _rt is None:
        _rt = Runtime.build(settings)
    return _rt


@router.post("/demo/run")
def demo_run():
    """Run the full loop on a fresh in-memory ledger (safe to click repeatedly)."""
    global _rt
    _rt = Runtime.build(settings, ledger_path=":memory:")
    try:
        return run_demo(_rt)
    except GuardViolation as e:
        raise HTTPException(409, e.to_dict()) from e


@router.get("/ledger")
def ledger(lineage: str | None = None, kind: str | None = None):
    return [e.__dict__ for e in runtime().ledger.entries(lineage, kind)]


@router.get("/ledger/verify")
def ledger_verify():
    ok, bad = runtime().ledger.verify()
    return {"chain_ok": ok, "first_bad_seq": bad}


@router.get("/studio/rows")
def studio_rows():
    """Row data for AG Grid / AG Studio widgets."""
    rows = transaction_rows(runtime().ledger)
    return {"rows": rows, "kpis": kpis(rows)}


# ---- run sessions ----------------------------------------------------------


class StartRun(BaseModel):
    mandate: Mandate | None = None
    needs: list[dict] | None = None


class Approver(BaseModel):
    approver: str = "ops@acme.example"
    reason: str = "rejected by approver"


def _run(run_id: str) -> runs.Run:
    if run_id not in runs.RUNS:
        raise HTTPException(404, "unknown run")
    return runs.RUNS[run_id]


def _guarded(fn, *args):
    """Guards and refused transitions are conflicts the UI can show, not server errors."""
    try:
        return fn(*args)
    except GuardViolation as e:
        raise HTTPException(409, e.to_dict()) from e
    except PayPalAPIError as e:
        # e.g. ORDER_NOT_APPROVED if the buyer closed the popup, INSTRUMENT_DECLINED in sandbox.
        raise HTTPException(502, e.to_dict()) from e
    except KeyError as e:
        raise HTTPException(404, f"unknown lineage {e}") from e
    except ValueError as e:
        raise HTTPException(409, {"guard": "InvalidTransition", "message": str(e)}) from e


@router.post("/runs")
async def start_run(body: StartRun | None = None):
    body = body or StartRun()
    try:
        run = await runs.start_run(settings, body.mandate, body.needs)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return run.snapshot()


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    return _run(run_id).snapshot()


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, follow: bool = True):
    """SSE: replay the backlog, then stream live events until the run completes."""
    run = _run(run_id)

    async def stream():
        q: asyncio.Queue = asyncio.Queue()
        backlog = list(run.events)
        run.subscribers.append(q)  # subscribe before yielding so nothing is missed between backlog and live
        try:
            seen = len(backlog)
            for e in backlog:
                yield f"data: {json.dumps(e)}\n\n"
            if not follow or run.complete:
                return
            while True:
                try:
                    e = await asyncio.wait_for(q.get(), timeout=15)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if e is None:
                    return
                if e["seq"] >= seen:
                    yield f"data: {json.dumps(e)}\n\n"
        finally:
            run.subscribers.remove(q)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/runs/{run_id}/ledger")
def run_ledger(run_id: str, lineage: str | None = None):
    """This run's sealed evidence, with the chain check, so the UI can show why it can be trusted."""
    ledger = _run(run_id).rt.ledger
    ok, bad = ledger.verify()
    return {"chain_ok": ok, "first_bad_seq": bad, "entries": [e.__dict__ for e in ledger.entries(lineage)]}


@router.post("/runs/{run_id}/decisions/{lineage}/approve")
def approve(run_id: str, lineage: str, body: Approver | None = None):
    _guarded(runs.step_approve, _run(run_id), lineage, (body or Approver()).approver)
    return _run(run_id).snapshot()


@router.post("/runs/{run_id}/decisions/{lineage}/reject")
def reject(run_id: str, lineage: str, body: Approver | None = None):
    b = body or Approver()
    _guarded(runs.step_reject, _run(run_id), lineage, b.approver, b.reason)
    return _run(run_id).snapshot()


@router.post("/runs/{run_id}/orders/{lineage}/prepare")
def prepare(run_id: str, lineage: str):
    prep = _guarded(runs.step_prepare_order, _run(run_id), lineage)
    return {"order_id": prep["order"]["id"], "status": prep["order"].get("status"), "amount": prep["seal"]["amount"]}


@router.post("/runs/{run_id}/orders/{lineage}/capture")
def capture(run_id: str, lineage: str):
    cap = _guarded(runs.step_capture_order, _run(run_id), lineage)
    return {"capture_id": cap["id"], "status": cap["status"], "amount": cap["amount"]}


@router.post("/runs/{run_id}/orders/{lineage}/retry")
def retry(run_id: str, lineage: str):
    return _guarded(runs.step_retry_order, _run(run_id), lineage)


@router.post("/runs/{run_id}/attack")
def attack(run_id: str):
    d = runs.step_attack(_run(run_id))
    return {"route": d.route, "reasons": d.reasons, "latency_ms": d.latency_ms}
