import asyncio
import json
import threading
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from . import runs
from .config import settings
from .core.errors import GuardViolation, WebhookUnverified
from .core.ledger import EvidenceLedger, open_ledger
from .domain.models import DeliveryReport, Mandate
from .integrations.llm import make_llm
from .integrations.paypal import PayPalAPIError, make_gateway
from .orchestrator import Runtime, run_demo
from .stages import s05_verify, s08_defend, s10_learn
from .stages.s09_observe import kpis, transaction_rows, with_supplier_trust

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


_history = None
_history_lock = threading.Lock()


def history_ledger():
    """Seeded history, built once per process through the real step functions (app/seed.py)."""
    global _history
    with _history_lock:  # two first requests must not both pay for (and race on) the build
        if _history is None:
            from .seed import build_history

            _history = build_history()
    return _history


@router.get("/studio/rows")
def studio_rows(run_id: str | None = None, history: bool = False):
    """Row data for AG Grid / AG Studio widgets. `history=true` adds the seeded history, tagged
    `source: "seeded"`, so a run can be read against ~30 past mandates."""
    # An unknown run (e.g. wiped by a backend restart) is a 404, never another run's data.
    if run_id or runs.RUNS:
        run = _run(run_id) if run_id else list(runs.RUNS.values())[-1]
        rows = [{**r, "source": "run"} for r in transaction_rows(run.rt.ledger, run.mandate_lineage)]
    else:
        rows = [{**r, "source": "demo"} for r in transaction_rows(runtime().ledger)]
    if history:
        rows += [{**r, "source": "seeded"} for r in transaction_rows(history_ledger())]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
    rows = with_supplier_trust(rows)
    return {"rows": rows, "kpis": kpis(rows)}


@router.get("/studio/lineage/{lineage_id}")
def studio_lineage(lineage_id: str):
    """One purchase's sealed ledger entries, from whichever ledger holds it (runs first, then seeded history)."""
    candidates = [("run", r.rt.ledger) for r in reversed(list(runs.RUNS.values()))] + [("seeded", history_ledger())]
    for source, ledger in candidates:
        entries = ledger.entries(lineage_id)
        if entries:
            ok, bad = ledger.verify()
            return {
                "source": source,
                "lineage_id": lineage_id,
                "chain_ok": ok,
                "first_bad_seq": bad,
                "entries": [e.__dict__ for e in entries],
            }
    raise HTTPException(404, f"no ledger entries for {lineage_id}")


@router.get("/studio/calibrations")
def studio_calibrations():
    """Mandate v1 -> v2 changes that stage 10 already made across the seeded history."""
    return {"calibrations": s10_learn.calibrations(history_ledger())}


@router.get("/studio/history/verify")
def history_verify():
    ok, bad = history_ledger().verify()
    return {"chain_ok": ok, "first_bad_seq": bad, "entries": len(history_ledger().entries())}


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
        # A live run makes blocking HTTP calls (Channel3, PayPal) for seconds. Running it on a worker thread with
        # its own loop keeps health checks, SSE keepalives and other requests responsive meanwhile.
        run = await run_in_threadpool(lambda: asyncio.run(runs.start_run(settings, body.mandate, body.needs)))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return run.snapshot()


@router.get("/runs/latest")
def get_latest_run():
    if not runs.RUNS:
        raise HTTPException(404, "no active runs")
    return list(runs.RUNS.values())[-1].snapshot()


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    return _run(run_id).snapshot()


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, follow: bool = True):
    """SSE: replay the backlog, then stream live events until the run completes."""
    run = _run(run_id)

    async def stream():
        q: asyncio.Queue = asyncio.Queue()
        sub = (asyncio.get_running_loop(), q)
        backlog = list(run.events)
        run.subscribers.append(sub)  # subscribe before yielding so nothing is missed between backlog and live
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
            run.subscribers.remove(sub)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/runs/{run_id}/calibration")
def run_calibration(run_id: str):
    """What stage 10 would change for this run's mandate right now. Read-only: nothing is written."""
    run = _run(run_id)
    p = s10_learn.plan(run.rt.ledger, run.mandate, run.mandate_lineage)
    before = run.mandate.model_dump(mode="json")
    after = p["new"].model_dump(mode="json") if p["new"] else None
    return {
        "changed": after is not None,
        "changes": p["changes"],
        "trust": p["trust"],
        "before": before,
        "after": after,
        "diff": s10_learn.mandate_diff(before, after) if after else [],
    }


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
    if ledger and lineage:
        s08_defend.sync_outcome(ledger, case, lineage)  # a resolved case teaches stage 10, once
    receipt = _return_receipt(ledger or fallback_ledger(), lineage or f"DISPUTE-{case.dispute_id}", case.dispute_id)
    a = s08_defend.assess(case, ledger, lineage, date.today(), return_address_set=bool(settings.return_address), return_receipt=receipt)
    return case, ledger, lineage, a


def _return_receipt(ledger: EvidenceLedger, lineage: str, dispute_id: str) -> dict | None:
    e = next((e for e in reversed(ledger.entries(lineage, "return_received")) if e.payload["dispute_id"] == dispute_id), None)
    return {**e.payload, "at": e.created_at} if e else None


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
                "reason_label": a["reason_label"],
                "state_note": a["state_note"],
                "flags": a["flags"],
            }
        )
    return sorted(out, key=lambda r: (r["days_left"] is None, r["days_left"] or 0))


@router.get("/disputes/{dispute_id}")
def get_dispute(dispute_id: str):
    case, _, _, a = _case(dispute_id)
    drafts = {o["option"]: s08_defend.draft_reply(case, a, o["option"]) for o in a["options"]}
    return _dec({"case": _case_json(case), "assessment": a, "drafts": drafts, "timeline": s08_defend.timeline(case, a)})


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
    d = case.as_dispute(lineage)
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
            disputes_gateway(),
            ledger or fallback_ledger(),
            case,
            a,
            option=body.option,
            note=body.note,
            approver=body.approver,
            return_address=settings.return_address,
        )
    )
    case2, _, _, a2 = _case(dispute_id)
    return _dec({"paypal": resp, "case": _case_json(case2), "assessment": a2})


class SimulateDispute(BaseModel):
    lineage_id: str
    reason: str = "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED"
    note: str = "its not working now. it was working fine and then it stopped. it seems i will have to return it"
    amount: str | None = None
    stage: str = "INQUIRY"


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
        stage=body.stage,
        due=(date.today() + timedelta(days=10)).isoformat(),
        created=datetime.now(UTC).isoformat(),
    )
    return {"dispute_id": d["dispute_id"]}


class SimulateResolve(BaseModel):
    outcome_code: str = "RESOLVED_SELLER_FAVOUR"


@router.post("/disputes/{dispute_id}/simulate-resolve")
def simulate_resolve(dispute_id: str, body: SimulateResolve):
    """Replay only: PayPal closes the case, so the outcome sync (and stage 10) can be shown end to end."""
    if not settings.replay_mode:
        raise HTTPException(409, "live mode: PayPal resolves disputes")
    try:
        disputes_gateway().resolve_dispute(dispute_id, body.outcome_code)
    except PayPalAPIError as e:
        raise HTTPException(404, e.to_dict()) from e
    case, _, _, a = _case(dispute_id)
    return _dec({"case": _case_json(case), "assessment": a})


class DeliveryBody(BaseModel):
    lineage_id: str
    carrier: str
    tracking_number: str
    tracking_status: str  # DELIVERED | IN_TRANSIT | LOST | NONE
    delivered_on: str | None = None
    due_by: str


@router.post("/deliveries")
def record_delivery(body: DeliveryBody):
    """Stage 5 for any sealed purchase, live or replay: carrier tracking becomes sealed delivery proof
    that stage 8 can cite. The VERIFIED gate token stays on the server."""
    ledger = next((led for led in evidence_ledgers() if led.latest(body.lineage_id, "seal")), None)
    if ledger is None:
        raise HTTPException(404, "no sealed purchase with that lineage")
    seal = ledger.latest(body.lineage_id, "seal")
    report = _guarded(lambda: DeliveryReport(**body.model_dump(exclude={"lineage_id"})))
    out = s05_verify.verify_delivery(ledger, settings.gate_secret, body.lineage_id, seal.payload["order_id"], report)
    return {"verdict": out["verdict"], "problems": out["problems"]}


class ReturnReceived(BaseModel):
    condition: str = "ITEM_RECEIVED"  # what was in the parcel: see s08_defend.RETURN_CONDITIONS
    note: str = ""
    inspector: str = "ops@acme.example"


@router.post("/disputes/{dispute_id}/return-received")
def return_received(dispute_id: str, body: ReturnReceived):
    """A person opened the returned parcel. Sealed before any acknowledgement goes to PayPal, because
    ITEM_RECEIVED releases the refund at once and buyer-uploaded tracking proves nothing about contents."""
    if body.condition not in s08_defend.RETURN_CONDITIONS:
        raise HTTPException(422, f"condition must be one of {sorted(s08_defend.RETURN_CONDITIONS)}")
    case, ledger, lineage, _ = _case(dispute_id)
    if "acknowledge_return_item" not in case.actions:
        raise HTTPException(409, "PayPal isn't expecting a return on this case")
    led, lid = ledger or fallback_ledger(), lineage or f"DISPUTE-{dispute_id}"
    if _return_receipt(led, lid, dispute_id):
        raise HTTPException(409, "return already inspected for this dispute")
    led.append(lid, "8-defend", "return_received", {"dispute_id": dispute_id, **body.model_dump()})
    case2, _, _, a = _case(dispute_id)
    return _dec({"case": _case_json(case2), "assessment": a})


class SimulateReturn(BaseModel):
    carrier: str = "UPS"
    tracking_number: str = "1Z999AA10123456784"


@router.post("/disputes/{dispute_id}/simulate-return")
def simulate_return(dispute_id: str, body: SimulateReturn):
    """Replay only: the buyer accepts our return offer and uploads return tracking, as in the live sandbox."""
    if not settings.replay_mode:
        raise HTTPException(409, "live mode: the buyer ships the return in the Resolution Center")
    try:
        disputes_gateway().buyer_ships_return(dispute_id, body.carrier, body.tracking_number)
    except PayPalAPIError as e:
        raise HTTPException(409, e.to_dict()) from e
    case, _, _, a = _case(dispute_id)
    return _dec({"case": _case_json(case), "assessment": a})


# --- PayPal webhooks (stage 7) ------------------------------------------------------------------------


@router.post("/webhooks/paypal")
async def paypal_webhook(request: Request):
    """PayPal's delivery target. Verified against the raw bytes it sent, de-duplicated by event id (a retry
    gets 200 with duplicate=true, so PayPal stops retrying), then stored in the ledger."""
    raw = await request.body()
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Body is not valid JSON.") from None
    if not isinstance(event, dict) or not event.get("id"):
        raise HTTPException(400, "Not a PayPal webhook event: no id.")
    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        # Verification is a blocking HTTP call to PayPal; keep it off the event loop.
        return await run_in_threadpool(runtime().inbox.receive, headers, event, raw)
    except WebhookUnverified as e:
        raise HTTPException(401, e.to_dict()) from e


@router.get("/webhooks")
def webhook_events():
    return {"events": runtime().inbox.listing(), "verification": "live" if settings.paypal_live else "replay"}


@router.post("/webhooks/{event_id}/replay")
def webhook_replay(event_id: str):
    try:
        return runtime().inbox.replay(event_id)
    except KeyError:
        raise HTTPException(404, f"No stored webhook event {event_id}.") from None


class SimulatedWebhook(BaseModel):
    event_type: str = "PAYMENT.CAPTURE.COMPLETED"
    lineage_id: str | None = None
    event_id: str | None = None  # send the same id twice to watch the duplicate being ignored


@router.post("/webhooks/simulate")
def webhook_simulate(body: SimulatedWebhook):
    """Feeds a synthetic event through the same inbox as a real delivery. Replay mode only: live mode checks
    PayPal's signature, which a synthetic event cannot carry."""
    if not settings.replay_mode:
        raise HTTPException(409, "Simulation is replay-only: live mode verifies real PayPal signatures.")
    event = {
        "id": body.event_id or f"WH-SIM-{uuid.uuid4().hex[:12].upper()}",
        "event_type": body.event_type,
        "summary": f"Simulated {body.event_type}",
        "create_time": datetime.now(UTC).isoformat(timespec="seconds"),
        "resource": {"id": f"SIM-{uuid.uuid4().hex[:10].upper()}", "custom_id": body.lineage_id},
    }
    out = runtime().inbox.receive({"paypal-transmission-sig": "simulated"}, event, json.dumps(event).encode())
    return {**out, "event": event}
