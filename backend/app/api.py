import asyncio
import json
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from . import runs
from .config import settings
from .core.errors import GuardViolation
from .core.ledger import EvidenceLedger, open_ledger
from .domain.models import Mandate
from .integrations.llm import make_llm
from .integrations.paypal import PayPalAPIError, make_gateway
from .orchestrator import Runtime, run_demo
from .stages import s08_defend
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
def studio_rows(run_id: str | None = None):
    """Row data for AG Grid / AG Studio widgets."""
    # An unknown run (e.g. wiped by a backend restart) is a 404, never another run's data.
    if run_id or runs.RUNS:
        run = _run(run_id) if run_id else list(runs.RUNS.values())[-1]
        rows = transaction_rows(run.rt.ledger, run.mandate_lineage)
    else:
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
    run = _run(run_id)
    if lineage and not (lineage == run.mandate_lineage or lineage.startswith(run.mandate_lineage + ".")):
        raise HTTPException(404, "lineage is not part of this run")
    ok, bad = run.rt.ledger.verify()  # the chain is checked whole; the entries shown are this run's
    return {"chain_ok": ok, "first_bad_seq": bad, "entries": [e.__dict__ for e in run.rt.ledger.entries(lineage or run.mandate_lineage)]}


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


# ---- disputes (stage 8) --------------------------------------------------------------------------

_disputes_gw = None
_dispute_ledger: EvidenceLedger | None = None


def disputes_gateway():
    """One gateway for the dispute desk: the live sandbox, or one shared replay double for demos."""
    global _disputes_gw
    if _disputes_gw is None:
        _disputes_gw = make_gateway(settings)
    return _disputes_gw


def evidence_ledgers() -> list[EvidenceLedger]:
    """Where a sealed record can live: the persistent live ledger, then each run's ledger (newest first)."""
    out = [] if settings.replay_mode else [open_ledger(settings.ledger_path)]
    for r in reversed(list(runs.RUNS.values())):
        if r.rt.ledger not in out:
            out.append(r.rt.ledger)
    return out


def fallback_ledger() -> EvidenceLedger:
    """Where to record a response to a dispute we couldn't match to a sealed order."""
    global _dispute_ledger
    if not settings.replay_mode:
        return open_ledger(settings.ledger_path)
    _dispute_ledger = _dispute_ledger or EvidenceLedger(":memory:")
    return _dispute_ledger


def _case(dispute_id: str):
    try:
        raw = disputes_gateway().get_dispute(dispute_id)
    except PayPalAPIError as e:
        raise HTTPException(404 if e.status == 404 else 502, e.to_dict()) from e
    case = s08_defend.parse_paypal_dispute(raw)
    ledger, lineage = s08_defend.locate(case, evidence_ledgers())
    return case, ledger, lineage, s08_defend.assess(case, ledger, lineage, date.today())


def _dec(obj):
    """Money stays a decimal string on the wire, as everywhere else in the API."""
    return jsonable_encoder(obj, custom_encoder={Decimal: lambda d: format(d, "f")})


def _case_json(case) -> dict:
    return _dec({**case.__dict__})


@router.get("/disputes")
def list_disputes():
    """Every open case with its recommendation, soonest deadline first."""
    try:
        items = disputes_gateway().list_disputes()
    except PayPalAPIError as e:
        raise HTTPException(502, e.to_dict()) from e
    out = []
    for d in items:
        case, _, _, a = _case(d["dispute_id"])
        out.append(
            {
                "case": _case_json(case),
                "recommended": a["recommended"],
                "win_odds": a["win_odds"],
                "days_left": a["days_left"],
                "lineage_found": a["facts"]["lineage_found"],
            }
        )
    return sorted(out, key=lambda r: (r["days_left"] is None, r["days_left"] or 0))


@router.get("/disputes/{dispute_id}")
def get_dispute(dispute_id: str):
    case, _, _, a = _case(dispute_id)
    drafts = {o["option"]: s08_defend.draft_reply(case, a, o["option"]) for o in a["options"]}
    return _dec({"case": _case_json(case), "assessment": a, "drafts": drafts})


class DraftBody(BaseModel):
    option: str


@router.post("/disputes/{dispute_id}/draft")
def polish_draft(dispute_id: str, body: DraftBody):
    """Template draft, reworded by Claude when a key is configured. The LLM only rewrites tone: the
    facts it may use are passed in, and the human still reads and approves before anything is sent."""
    case, _, _, a = _case(dispute_id)
    text = s08_defend.draft_reply(case, a, body.option)
    llm = make_llm(settings)
    polished = None
    if llm:
        polished = llm.text(
            "You edit a merchant's reply to a PayPal dispute. Keep every fact, number and commitment exactly as given; "
            "add no new facts, promises or legal claims. Make it courteous and under 120 words. Reply with the text only.",
            f"Buyer's note: {case.buyer_note!r}\nDraft reply:\n{text}",
        )
    return {"option": body.option, "text": polished or text, "source": "llm" if polished else "template"}


@router.get("/disputes/{dispute_id}/brief.pdf")
def dispute_brief(dispute_id: str):
    case, ledger, lineage, _ = _case(dispute_id)
    if not ledger:
        raise HTTPException(404, "no sealed record for this dispute, so there is no evidence brief")
    d = case.as_dispute().model_copy(update={"lineage_id": lineage})
    pdf = s08_defend.render_pdf(d, s08_defend.build_evidence(ledger, d))
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{dispute_id}-brief.pdf"'})


class RespondBody(BaseModel):
    option: str
    note: str
    approver: str = "ops@acme.example"


@router.post("/disputes/{dispute_id}/respond")
def respond_dispute(dispute_id: str, body: RespondBody):
    """D-4: nothing is sent to PayPal without this explicit human call. The recommendation is advice."""
    case, ledger, _, a = _case(dispute_id)
    resp = _guarded(
        lambda: s08_defend.respond(
            disputes_gateway(), ledger or fallback_ledger(), case, a, option=body.option, note=body.note, approver=body.approver
        )
    )
    case2, _, _, a2 = _case(dispute_id)
    return _dec({"paypal": resp, "case": _case_json(case2), "assessment": a2})


class SimulateDispute(BaseModel):
    lineage_id: str
    reason: str = "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED"
    note: str = "its not working now. it was working fine and then it stopped. it seems i will have to return it"
    amount: str | None = None


@router.post("/runs/{run_id}/disputes/simulate")
def simulate_dispute(run_id: str, body: SimulateDispute):
    """Replay only: the buyer opens a case on a settled item, shaped like a real sandbox dispute."""
    if not settings.replay_mode:
        raise HTTPException(409, "live mode: open disputes as the sandbox buyer in the Resolution Center")
    item = _guarded(lambda: _run(run_id).item(body.lineage_id))
    if not item.capture:
        raise HTTPException(409, "only a settled item can be disputed")
    d = disputes_gateway().open_dispute(
        lineage_id=body.lineage_id,
        capture_id=item.capture["id"],
        amount=body.amount or item.capture["amount"]["value"],
        reason=body.reason,
        note=body.note,
        item_name=item.title,
        due=(date.today() + timedelta(days=10)).isoformat(),
        created=f"{date.today().isoformat()}T09:00:00Z",
    )
    return {"dispute_id": d["dispute_id"]}
