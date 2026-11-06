"""Build the seeded history through the real step functions and summarise it.

    backend/.venv/bin/python backend/scripts/seed_history.py            # summary
    backend/.venv/bin/python backend/scripts/seed_history.py --rows     # also print every row

The API builds the same history in memory on first use (GET /api/studio/rows?history=true).
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.seed import build_history  # noqa: E402
from app.stages.s09_observe import kpis, transaction_rows  # noqa: E402

led = build_history()
rows = transaction_rows(led)
ok, bad = led.verify()
print(f"{len(led.entries())} ledger entries, chain {'verified' if ok else f'BROKEN at {bad}'}")
print(f"{len(rows)} purchases from {rows[-1]['created_at'][:10]} to {rows[0]['created_at'][:10]}")
print("routes   ", dict(Counter(r.get("route") for r in rows)))
print("status   ", dict(Counter(r.get("status", "-") for r in rows)))
print("disputes ", dict(Counter(r["dispute_outcome"] for r in rows if r.get("dispute_outcome"))))
print("kpis     ", json.dumps(kpis(rows)))
if "--rows" in sys.argv:
    for r in rows:
        print(json.dumps(r))
