"""The Studio assistant proxy: key stays server-side, the request is pinned, the stream passes through."""

import pytest
from fastapi.testclient import TestClient

from app import ai_proxy
from app.config import settings
from app.main import app

client = TestClient(app)


class FakeEvent:
    def __init__(self, type_: str, payload: str):
        self.type = type_
        self._payload = payload

    def model_dump_json(self) -> str:
        return self._payload


class FakeStream:
    def __init__(self, events):
        self._events = events
        self.closed = False

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for e in self._events:
            yield e

    async def close(self):
        self.closed = True


class FakeAnthropic:
    def __init__(self, events=()):
        self.calls: list[dict] = []
        self.stream = FakeStream(list(events))
        self.messages = self

    async def create(self, **params):
        self.calls.append(params)
        return self.stream


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")
    monkeypatch.setattr(settings, "llm_model", "claude-haiku-5-5")
    ai_proxy._hits.clear()


BODY = {"messages": [{"role": "user", "content": "hi"}], "system": "be brief"}


def test_config_reports_whether_the_assistant_is_available(monkeypatch):
    assert client.get("/api/ai/config").json() == {"configured": True, "model": "claude-haiku-5-5"}
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    assert client.get("/api/ai/config").json()["configured"] is False


def test_no_key_is_503_and_nothing_is_sent(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    fake = FakeAnthropic()
    monkeypatch.setattr(ai_proxy, "_anthropic", lambda: fake)
    assert client.post("/api/ai/messages", json=BODY).status_code == 503
    assert fake.calls == []


def test_request_is_pinned_before_it_goes_upstream(monkeypatch):
    fake = FakeAnthropic()
    monkeypatch.setattr(ai_proxy, "_anthropic", lambda: fake)
    body = {
        **BODY,
        "model": "claude-fable-5-1",  # the browser cannot choose a pricier model
        "max_tokens": 10_000_000,
        "thinking": {"type": "enabled", "budget_tokens": 50_000},
        "temperature": 1,
        "tool_choice": {"type": "tool", "name": "add_widget"},
        "tools": [{"name": "add_widget", "description": "d", "input_schema": {"type": "object"}}],
    }
    assert client.post("/api/ai/messages", json=body).status_code == 200
    (params,) = fake.calls
    assert params["model"] == "claude-haiku-5-5"
    assert params["max_tokens"] == ai_proxy.MAX_OUTPUT_TOKENS
    assert params["thinking"] == {"type": "disabled"}
    assert params["tool_choice"] == {"type": "auto"}
    assert params["stream"] is True
    assert "temperature" not in params
    assert params["tools"][0]["name"] == "add_widget"


def test_sse_stream_passes_through_and_is_closed(monkeypatch):
    fake = FakeAnthropic(
        [
            FakeEvent("message_start", '{"type":"message_start"}'),
            FakeEvent("content_block_delta", '{"type":"content_block_delta","delta":{"text":"Hi"}}'),
            FakeEvent("message_stop", '{"type":"message_stop"}'),
        ]
    )
    monkeypatch.setattr(ai_proxy, "_anthropic", lambda: fake)
    r = client.post("/api/ai/messages", json=BODY)
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.text == (
        'event: message_start\ndata: {"type":"message_start"}\n\n'
        'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"text":"Hi"}}\n\n'
        'event: message_stop\ndata: {"type":"message_stop"}\n\n'
    )
    assert fake.stream.closed


@pytest.mark.parametrize("body", [{}, {"messages": []}, {"messages": "nope"}, {"messages": [{}], "tools": [{}] * 65}])
def test_malformed_requests_are_400(monkeypatch, body):
    monkeypatch.setattr(ai_proxy, "_anthropic", lambda: FakeAnthropic())
    assert client.post("/api/ai/messages", json=body).status_code == 400


def test_non_object_json_is_400(monkeypatch):
    monkeypatch.setattr(ai_proxy, "_anthropic", lambda: FakeAnthropic())
    assert client.post("/api/ai/messages", json=["not", "an", "object"]).status_code == 400


def test_rate_limit_applies_per_client_and_resets_with_the_window():
    for i in range(ai_proxy.RATE_LIMIT):
        assert ai_proxy._rate_limited("a", now=100.0 + i * 0.01) is False
    assert ai_proxy._rate_limited("a", now=101.0) is True
    assert ai_proxy._rate_limited("b", now=101.0) is False  # another client is unaffected
    assert ai_proxy._rate_limited("a", now=100.0 + ai_proxy.RATE_WINDOW_S + 1) is False


def test_route_returns_429_when_limited(monkeypatch):
    monkeypatch.setattr(ai_proxy, "_anthropic", lambda: FakeAnthropic())
    monkeypatch.setattr(ai_proxy, "RATE_LIMIT", 1)
    assert client.post("/api/ai/messages", json=BODY).status_code == 200
    assert client.post("/api/ai/messages", json=BODY).status_code == 429


def test_rate_limit_bounded_clients(monkeypatch):
    monkeypatch.setattr(ai_proxy, "MAX_TRACKED_CLIENTS", 5)
    ai_proxy._hits.clear()
    for i in range(10):
        ai_proxy._rate_limited(f"client-{i}", now=100.0)
    assert len(ai_proxy._hits) <= 5
    assert "client-9" in ai_proxy._hits


def test_client_id_handles_render_proxy_headers():
    class DummyRequest:
        def __init__(self, headers, host="10.0.0.1"):
            self.headers = headers
            self.client = type("Client", (), {"host": host})()

    req1 = DummyRequest({"render-client-ip": "198.51.100.4", "x-forwarded-for": "203.0.113.1, 10.0.0.1"})
    assert ai_proxy._client_id(req1) == "198.51.100.4"

    req2 = DummyRequest({"x-forwarded-for": "203.0.113.5, 10.0.0.1"})
    assert ai_proxy._client_id(req2) == "203.0.113.5"

    req3 = DummyRequest({})
    assert ai_proxy._client_id(req3) == "10.0.0.1"
