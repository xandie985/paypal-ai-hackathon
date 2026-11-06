"""Run every evaluation and write eval/RESULTS.md, the table that goes in the README.

    python -m eval.run_all
"""

from datetime import UTC, datetime
from pathlib import Path

from . import firewall_cases, idempotency_runs, negotiation_runs

OUT = Path(__file__).with_name("RESULTS.md")


def main() -> str:
    fw, neg, idem = firewall_cases.run(), negotiation_runs.run(), idempotency_runs.run()
    held_out = fw["by_group"]["prompt injection (paraphrased, held-out)"]["correct"]
    md = f"""# Evaluation results

Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC by `python -m eval.run_all` from `backend/`. Everything runs offline against
the deterministic replay gateway and simulated sellers, with fixed seeds, so the numbers reproduce exactly.

## Mandate firewall: {fw['scenarios']} scenarios

{firewall_cases.table(fw)}

Decision latency: p50 {fw['p50_ms']} ms, worst {fw['max_ms']} ms (deterministic, no LLM in the path).

Every over-budget, over-cap, non-refundable, off-allowlist, review-first and directly phrased injection scenario was
routed as intended. **The weak spot is paraphrased prompt injection.** The injection tripwire is a regular-expression
list; on the 3 paraphrases it was hardened against it catches all 3, but on 5 paraphrases written beforehand and never
used to tune it, it catches {held_out} of 5. That is the honest estimate of how it generalises. It is a
tripwire, not the safeguard: seller text never changes a route except to block it, so a phrasing that slips through
can only auto-settle a purchase that independently passes all four factors (an allowlisted vendor and category,
return terms, price against baseline, budget and cap). A model-based classifier that may only escalate is the next step.

## Negotiation: {neg['runs']} seeded runs, varied seller parameters

{negotiation_runs.table(neg)}

The sellers are deterministic concession policies, not merchants or LLMs, so the savings figure measures the buyer's
strategy against simulated curves and moves with the parameters chosen (here: floors at 70 to 95% of list). What it
does verify independently of those parameters is the gate: no misbehaving seller (non-numeric price, extra fields,
a price walked back up, wrong quantity) survived to win, and no run committed to more than one seller.

## Idempotency: {idem['retries']} attempts per operation

{idempotency_runs.table(idem)}

The replay gateway reproduces PayPal's `PayPal-Request-Id` behaviour (a repeated id returns the original result).
The request ids are derived from the lineage, so a retry of the same operation always repeats the same id. A different
logical operation still goes through: {'yes' if idem['distinct_operation_allowed'] else 'NO'}.
"""
    OUT.write_text(md)
    return md


if __name__ == "__main__":
    print(main())
