"""Who may start a run against the real PayPal sandbox, and how often.

A sandbox run creates real orders in the project's PayPal sandbox and charges its saved wallet (test money). On a
public deployment that is an open door to the owner's sandbox, so it is off unless `ALLOW_SANDBOX_RUNS` is set, capped
in size, and rate-limited per client and across all clients. The limits are per process, like the run store."""

import threading
import time
from collections import deque

WINDOW_S = 3600.0
PER_CLIENT = 3
MAX_TRACKED = 1024

_lock = threading.Lock()
_by_client: dict[str, deque[float]] = {}
_all: deque[float] = deque()


def reset() -> None:
    with _lock:
        _by_client.clear()
        _all.clear()


def allow(client: str, global_limit: int, now: float | None = None) -> bool:
    """Record one sandbox run for `client` if both limits have room. False means refuse; nothing is recorded."""
    now = time.monotonic() if now is None else now
    cutoff = now - WINDOW_S
    with _lock:
        while _all and _all[0] <= cutoff:
            _all.popleft()
        mine = _by_client.get(client)
        if mine is not None:
            while mine and mine[0] <= cutoff:
                mine.popleft()
        if len(_all) >= global_limit or (mine is not None and len(mine) >= PER_CLIENT):
            return False
        if mine is None:
            if len(_by_client) >= MAX_TRACKED:
                for k in [k for k, v in _by_client.items() if not v or v[-1] <= cutoff]:
                    del _by_client[k]
                if len(_by_client) >= MAX_TRACKED:
                    return False
            mine = _by_client[client] = deque()
        mine.append(now)
        _all.append(now)
        return True
