"""Server-side proxy for the AG Studio assistant.

The browser adapter (frontend/src/studio/claudeAdapter.ts) POSTs an Anthropic Messages request here. This
adds the API key, pins the model and a token cap, forces thinking off (the adapter rebuilds history from
Studio's own items and has no thinking blocks to replay), and streams the SSE reply straight back. The key
never reaches the browser; a per-client rate limit bounds spend because the route is otherwise open.
"""

import json
import time
from collections import defaultdict, deque

import anthropic
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .config import settings

router = APIRouter(prefix="/api/ai")

MAX_OUTPUT_TOKENS = 8_000
MAX_BODY_BYTES = 2_000_000
MAX_TOOLS = 64
RATE_LIMIT = 40  # requests per window per client; one assistant turn is one request
RATE_WINDOW_S = 60.0

_ALLOWED_FIELDS = ("system", "messages", "tools", "tool_choice", "max_tokens")
_hits: dict[str, deque[float]] = defaultdict(deque)
_client: anthropic.AsyncAnthropic | None = None


def _anthropic() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": {"message": message}}, status_code=status)


def _client_id(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limited(client: str, now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    window = _hits[client]
    while window and now - window[0] > RATE_WINDOW_S:
        window.popleft()
    if len(window) >= RATE_LIMIT:
        return True
    window.append(now)
    return False


def build_params(body: dict) -> dict:
    """The request that goes upstream: whitelisted fields only, with model, token cap and thinking pinned."""
    params = {k: body[k] for k in _ALLOWED_FIELDS if body.get(k) is not None}
    params["model"] = settings.llm_model
    params["max_tokens"] = min(int(params.get("max_tokens") or MAX_OUTPUT_TOKENS), MAX_OUTPUT_TOKENS)
    params["thinking"] = {"type": "disabled"}
    tools = params.get("tools")
    if isinstance(tools, list) and len(tools) > MAX_TOOLS:
        raise ValueError(f"At most {MAX_TOOLS} tools per request.")
    # Forced tool use is rejected by the newer models; the adapter steers from the prompt instead.
    choice = params.get("tool_choice")
    if isinstance(choice, dict) and choice.get("type") not in ("auto", "none"):
        params["tool_choice"] = {"type": "auto"}
    if not isinstance(params.get("messages"), list) or not params["messages"]:
        raise ValueError("messages must be a non-empty list.")
    return params


@router.get("/config")
def ai_config():
    """Tells the UI whether to offer the assistant at all (it is hidden when no key is configured)."""
    return {"configured": bool(settings.anthropic_api_key), "model": settings.llm_model}


@router.post("/messages")
async def ai_messages(request: Request):
    if not settings.anthropic_api_key:
        return _error(503, "The AI assistant is not configured: set ANTHROPIC_API_KEY on the server.")
    if _rate_limited(_client_id(request)):
        return _error(429, "Too many assistant requests. Wait a minute and try again.")
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        return _error(413, "Request is too large.")
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("Body must be a JSON object.")
        params = build_params(body)
    except ValueError as e:
        return _error(400, str(e))

    try:
        upstream = await _anthropic().messages.create(**params, stream=True)
    except anthropic.APIStatusError as e:
        return _error(e.status_code, e.message)
    except anthropic.APIConnectionError:
        return _error(502, "Could not reach the model provider.")

    async def events():
        try:
            async for event in upstream:
                yield f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"
        except anthropic.APIError as e:
            payload = {"type": "error", "error": {"type": "api_error", "message": str(e.message)}}
            yield f"event: error\ndata: {json.dumps(payload)}\n\n"
        finally:
            # Studio's Stop button aborts the browser request, which cancels this generator.
            await upstream.close()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
