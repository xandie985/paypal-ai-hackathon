# PactGuard AI

**An autonomous purchasing agent with a spend mandate it cannot talk its way past.** You hand it a budget and a mandate. It finds products on the real retail graph (Channel3), negotiates with sellers, and pays through PayPal. A deterministic firewall stands in front of every money movement, and every decision is sealed in a tamper-evident ledger. When a purchase is disputed, the agent defends it with evidence it sealed *before* the dispute. What happens next is read back into a tighter mandate, and the whole history is explorable in an embedded **AG Studio** command center.

Built for the [PayPal AI Hackathon 2026](https://paypalaihackathon.devpost.com/).

> **Live demo:** _add the Render URL here after deploying (see "Deploy" below)._ It opens in replay mode, so it never depends on sandbox uptime and judges cannot spend our sandbox.

## The loop

**Delegate → Discover → Negotiate → Govern → Settle & seal → Verify → Reconcile → Pay out → Defend → Learn**

1. **Delegate.** A mandate (budget, auto-approve threshold, per-transaction cap, vendor allowlist, return policy) is hashed into the root of a lineage ID. Every later call and ledger row carries it.
2. **Discover and negotiate.** Channel3 gives a retail baseline. The buyer negotiates with several sellers over three bounded turns. Every seller message must pass a schema gate or that seller is dropped, and exactly one seller can be committed.
3. **Govern.** A four-factor firewall (warrant, reversibility, price against baseline, budget) routes each purchase to `AUTO_SETTLE`, `HUMAN_APPROVAL` or `BLOCKED` in well under a millisecond, with no LLM in the path.
4. **Settle and seal.** PayPal Orders v2 with a lineage-derived `PayPal-Request-Id`, so a retry can never charge twice. The terms the buyer agreed to are sealed in the ledger, and capture refuses to run without that seal.
5. **Verify, reconcile, pay out.** A payout needs both a `VERIFIED` (delivery) and a `RECONCILED` (invoice forensics) gate token. Webhooks are verified against the raw bytes, de-duplicated and stored.
6. **Defend.** On a dispute, the desk assembles a PDF brief from the sealed record, estimates the win odds, and drafts the response. A person decides. Nothing reaches PayPal without a click.
7. **Learn.** Dispute outcomes and delivery proof feed a per-supplier trust score and propose mandate v2, shown as a before/after diff.

## Run it

```bash
make setup      # venv, npm install, copies .env.example to .env
make test       # 155 tests
make backend    # API on :8000 (REPLAY_MODE=true runs everything offline)
make frontend   # UI on :5173, in a second terminal
```

`make serve` builds the frontend and serves both from one process on :8000, which is the shape that runs on Render.

To use the live sandbox, set `REPLAY_MODE=false` and fill in the PayPal and Channel3 keys in `.env`. To enable the Studio assistant, set `ANTHROPIC_API_KEY`; `LLM_MODEL` picks the model (we run `claude-haiku-5-5`). The AG Studio licence key goes in `frontend/.env.local` as `VITE_AG_STUDIO_LICENSE`. It ships in the browser bundle by design, so it is the only key that ever does.

### Deploy

[`render.yaml`](render.yaml) and the [`Dockerfile`](Dockerfile) define one web service that serves the API and the built frontend from a single process. It runs a single worker, because run sessions live in process memory. Create it from the Blueprint, fill in the secrets Render asks for, and keep `REPLAY_MODE=true` for the public URL. The filesystem is ephemeral, so the ledger resets on restart and the seeded history is rebuilt on demand. To receive real PayPal webhooks, register `https://<your-service>/api/webhooks/paypal` as a webhook in the sandbox app and set `PAYPAL_WEBHOOK_ID`.

## What is live and what is simulated

| Stage | State |
|---|---|
| 1 Delegate, 3 Govern, 4 Settle | Real code. **Live against the PayPal sandbox**: Orders v2, including saved-wallet (vault) capture with no popup, and the PayPal JS SDK approval button for orders that need a person. |
| 2 Discover | Real code. **Live against Channel3** (`/v1/search`), with a labelled retailer return-policy table because Channel3 does not return return terms. |
| 2 Negotiate | Real protocol, **simulated sellers**: deterministic concession policies, not merchants or LLMs. |
| 5 Verify, 6 Reconcile, 7 Payout, 10 Learn | Real code, **scripted inputs** in replay. Delivery proof can be recorded live. The Payouts v1 call has been run against the sandbox. |
| 7 Webhooks | Real endpoint and raw-body verification, unit-tested. Not yet checked against a real PayPal sandbox event. |
| 8 Defend | Reads **real sandbox disputes** and answers through PayPal's dispute actions. The multipart `provide-evidence` upload is verified against the replay gateway, not yet against a live case. |
| 9 Observe | Real. AG Studio over the ledger (`Purchases` and `Agent Activity` pages), with a seeded history of past purchases built through the same step functions. |
| 9 Observe, PayPal pages | Real code, **two data modes**. The Command Center's Revenue, Receivables, Cash and Catalogue pages read the merchant's own PayPal account (invoices, payments, catalog products, billing plans, Transaction Search for the last 31 days, payouts, balances) through `GET /api/studio/paypal`, and join `Transactions.capture_id` to `PayPal Transactions.id` so an agent purchase links directly to its PayPal settlement. **Live** (`REPLAY_MODE=false` with sandbox keys) reads the sandbox account itself (falls back to the replay fixture only when PayPal answers 403, e.g. Transaction Search is not enabled on the sandbox app; any other failure is shown as an error, never as fixture data); the public replay demo serves a small **fixed fixture** of PayPal-shaped responses (fictional merchant, dated 2026-11-05) through the same transformation code. The replay fixture includes purchase captures with the seeded history's `CAP-0000xx` IDs, so the agent-to-PayPal join works in replay too; it is a fixture, not your sandbox data. The live read has so far been exercised against a mock PayPal only. |

## Evaluation

`python -m eval.run_all` (from `backend/`) runs three offline, seeded evaluations and writes [`backend/eval/RESULTS.md`](backend/eval/RESULTS.md). The same checks run in `make test`.

| Evaluation | Result |
|---|---|
| **Firewall**, 55 scenarios with intended routes written down in advance | 51 routed as intended. Zero unsafe auto-settles for over-budget, over-cap, non-refundable, off-allowlist, review-first, agent-initiated payout, or directly phrased injection scenarios. Decision latency p50 0.03 ms. |
| **Negotiation**, 20 seeded runs, 19 misbehaving sellers injected | All 19 dropped by the schema gate, none won, no run committed to two sellers, never more than 3 turns. Savings averaged 18.5% against **simulated** sellers (range 3.7% to 27.7%), so treat that figure as a property of the simulation. |
| **Idempotency**, 10 retries of each money operation | Exactly 1 real side effect for order, capture, invoice, send, reminder and payout. |

**Known weak spot, stated plainly:** prompt-injection detection is a regex tripwire. It catches every direct phrasing we tried and the paraphrases it was tuned against, but only **1 of 5** paraphrases written beforehand and never used to tune it. It is a tripwire, not the safeguard: seller text never changes a route except to block it, so a phrasing that slips through can only auto-settle a purchase that independently passes all four factors. A model-based classifier that may only escalate is the next step.

## How each tool is used

| Tool | What we did with it |
|---|---|
| **PayPal** | REST APIs called directly: Orders v2 (create, capture, vault), Invoicing v2 (draft-first, then send), Payouts v1, Disputes (read, offer, message, evidence), and Webhooks (raw-body verification). We do not use `@paypal/agent-toolkit`: it has no spend cap, no idempotency discipline and no payout tool, which are the gaps the firewall, lineage-derived request IDs and gate tokens close. |
| **AG Grid / AG Studio** | The Command Center is a six-page AG Studio report grouped under **Agent** (`Purchases`, `Agent Activity`) and **PayPal account** (`Revenue`, `Receivables`, `Cash`, `Catalogue`): spend, savings by vendor, firewall routes and latency, human escalations, dispute outcomes beside supplier trust, and PayPal account reporting joined to agent captures via `capture_id`. Clicking a row opens its sealed lineage or PayPal detail drawer. A mandate v1 → v2 diff sits beside it. The Studio assistant runs on **Claude Haiku 5.5** through an adapter we wrote for Studio's `AgLlmAdapter` contract, with the key held server-side. |
| **Channel3** | Live product search for the retail baseline and candidate sellers. |
| **Render** | One Docker web service from `render.yaml`. Not yet deployed by us: that needs the account step. |
| **APIMatic** | **Not used yet.** We will record which payloads it checks here once it is, and not before. |
| **Anthropic Claude** | Optional, and never in the money path: rewording dispute drafts, and the Studio assistant. With no key, or in replay mode, templates are used. |

## Architecture

```
frontend/   React 19, Vite, Tailwind 4, AG Studio          Mission Control · Command Center
backend/
  app/stages/   s01..s10    one module per stage, pure functions over the ledger
  app/core/     ledger (hash-chained, append-only SQLite), lineage IDs, HMAC gate tokens, penny-exact money
  app/integrations/   PayPal (replay + sandbox), Channel3, Claude
  app/runs.py   run sessions: the loop behind step functions a UI can pause
  app/api.py    REST + SSE, webhooks, Studio rows and lineage   ·   app/ai_proxy.py  Studio assistant proxy
  app/studio_paypal.py   PayPal account tables for the Command Center's PayPal pages (live sandbox read or fixture)
  eval/         the three evaluations
```

## Research and planning

The research behind the project is in [`docs/`](docs/): problem decomposition, the literature, 12 verified user pain points, competitors, the idea ranking, and the implementation and execution plans ([`09`](docs/09-implementation-framework.md) maps every stage and guard to code and a test; [`10`](docs/10-execution-plan.md) is the phased plan and tracker; [`11`](docs/11-dashboard-ui-plan.md) is the UI plan).

## Credits

The Command Center's PayPal pages (Revenue, Receivables, Cash, Catalogue), their data sources and the PayPal account tables behind them are adapted from the PayPal AI Hackathon's AG Grid boilerplate, [paypaldev/hackathon-paypal-ag-grid-boilerplate](https://github.com/paypaldev/hackathon-paypal-ag-grid-boilerplate) (`lib/paypal.ts`, `lib/dashboard-data.ts`, `app/dashboard/studio/`). The boilerplate is ported to Python and React here, and its repository carries no licence file, so we use it as the hackathon's provided starting point.
