from fastapi import APIRouter, HTTPException

from .config import settings
from .core.errors import GuardViolation
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
