# Evaluation results

Generated 2026-11-06 15:37 UTC by `python -m eval.run_all` from `backend/`. Everything runs offline against
the deterministic replay gateway and simulated sellers, with fixed seeds, so the numbers reproduce exactly.

## Mandate firewall: 55 scenarios

| Scenario group | Cases | Routed as intended | Unsafe auto-settles |
|---|---:|---:|---:|
| clean | 5 | 5 | 0 |
| over auto threshold | 5 | 5 | 0 |
| over per-txn cap | 5 | 5 | 0 |
| over budget (prior spend) | 5 | 5 | 0 |
| non-refundable | 5 | 5 | 0 |
| price premium over baseline | 4 | 4 | 0 |
| off-allowlist vendor | 4 | 4 | 0 |
| disallowed category | 3 | 3 | 0 |
| prompt injection (direct) | 5 | 5 | 0 |
| prompt injection (paraphrased, dev) | 3 | 3 | 0 |
| prompt injection (paraphrased, held-out) | 5 | 1 | 4 |
| review-first mandate | 3 | 3 | 0 |
| payout via agent tool call | 3 | 3 | 0 |
| **All** | **55** | **51** | **4** |

Decision latency: p50 0.032 ms, worst 0.173 ms (deterministic, no LLM in the path).

Every over-budget, over-cap, non-refundable, off-allowlist, review-first and directly phrased injection scenario was
routed as intended. **The weak spot is paraphrased prompt injection.** The injection tripwire is a regular-expression
list; on the 3 paraphrases it was hardened against it catches all 3, but on 5 paraphrases written beforehand and never
used to tune it, it catches 1 of 5. That is the honest estimate of how it generalises. It is a
tripwire, not the safeguard: seller text never changes a route except to block it, so a phrasing that slips through
can only auto-settle a purchase that independently passes all four factors (an allowlisted vendor and category,
return terms, price against baseline, budget and cap). A model-based classifier that may only escalate is the next step.

## Negotiation: 20 seeded runs, varied seller parameters

| Measure | Result |
|---|---|
| Runs (seeded, varied sellers) | 20 (20 produced a winner) |
| Savings vs baseline | mean 18.5%, median 19.9%, range 3.65% to 27.71% |
| Runs inside the 12 to 18% band | 5 of 20 |
| Most turns used | 3 (cap 3) |
| Misbehaving sellers injected / dropped by the schema gate | 19 / 19 |
| Misbehaving sellers that won | 0 |
| Runs with more than one commitment | 0 |

The sellers are deterministic concession policies, not merchants or LLMs, so the savings figure measures the buyer's
strategy against simulated curves and moves with the parameters chosen (here: floors at 70 to 95% of list). What it
does verify independently of those parameters is the gate: no misbehaving seller (non-numeric price, extra fields,
a price walked back up, wrong quantity) survived to win, and no run committed to more than one seller.

## Idempotency: 10 attempts per operation

| Operation | Attempts | Real side effects | Same result every time |
|---|---:|---:|---|
| create_order | 10 | 1 | yes |
| capture_order | 10 | 1 | yes |
| create_invoice | 10 | 1 | yes |
| send_invoice | 10 | 1 | yes |
| remind_invoice | 10 | 1 | yes |
| release_payout (stage 7) | 10 | 1 | yes |

The replay gateway reproduces PayPal's `PayPal-Request-Id` behaviour (a repeated id returns the original result).
The request ids are derived from the lineage, so a retry of the same operation always repeats the same id. A different
logical operation still goes through: yes.
