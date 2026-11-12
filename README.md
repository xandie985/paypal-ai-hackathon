# PactGuard AI

**An autonomous purchasing agent with a spend mandate it cannot talk its way past.** You hand it a budget and a mandate. It finds products on the real retail graph (Channel3), negotiates with sellers, and pays through PayPal. A deterministic firewall stands in front of every money movement, and every decision is sealed in a tamper-evident ledger. When a purchase is disputed, the agent defends it with evidence it sealed *before* the dispute. What happens next is read back into a tighter mandate, and the whole history is explorable in an embedded **AG Studio** command center.

Built for the [PayPal AI Hackathon 2026](https://paypalaihackathon.devpost.com/).

> **Live demo:** [https://pactguard-ai.onrender.com](https://pactguard-ai.onrender.com). It opens in replay mode, so it never depends on sandbox uptime and judges cannot spend our sandbox. Licensed under [Apache-2.0](LICENSE).

## Try it (about two minutes)

No credentials are needed.

1. Open the live demo and press **Run agent**. Choose what to buy and how many in the "What to buy" list first if you like. The webcams settle automatically; the monitors and the microphone wait for you.
2. Press **Approve** on the monitor card, then pay it, then **Run post-purchase checks** on a settled purchase: delivery verified, invoice reconciled, a spoofed resubmission flagged, a payout refused, then released.
3. Press **Simulate prompt-injection attack** to watch the firewall block it, and read the evidence ledger ("chain verified").
4. Open **Command Center** for the seven-page AG Studio report. Run another agent in a second tab and watch the Live feed add it.
5. **Run 10-Stage Showcase** in the header runs the whole loop in about a second.

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
make test       # 191 tests
make backend    # API on :8000 (REPLAY_MODE=true runs everything offline)
make frontend   # UI on :5173, in a second terminal
```

`make serve` builds the frontend and serves both from one process on :8000, which is the shape that runs on Render.

To use the live sandbox, set `REPLAY_MODE=false` and fill in the PayPal and Channel3 keys in `.env`. To enable the Studio assistant, set `ANTHROPIC_API_KEY`; `LLM_MODEL` picks the model (we default to `claude-haiku-5-5`, as render.yaml does). The AG Studio licence key goes in `frontend/.env.local` as `VITE_AG_STUDIO_LICENSE`. It ships in the browser bundle by design, so it is the only key that ever does.

### Deploy

[`render.yaml`](render.yaml) and the [`Dockerfile`](Dockerfile) define one web service that serves the API and the built frontend from a single process. It runs a single worker, because run sessions live in process memory. Create it from the Blueprint, fill in the secrets Render asks for, and keep `REPLAY_MODE=true` for the public URL. The filesystem is ephemeral, so the ledger resets on restart and the seeded history is rebuilt on demand. To receive real PayPal webhooks, register `https://<your-service>/api/webhooks/paypal` as a webhook in the sandbox app and set `PAYPAL_WEBHOOK_ID`.

### Sandbox run button

A replay deployment can still offer one real run. Set `ALLOW_SANDBOX_RUNS=true` together with `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` and `PAYPAL_VAULT_ID`, and Mission Control shows **Run in PayPal sandbox** under the mandate (with a confirmation). That run alone uses the real sandbox: orders and captures are created in the project's PayPal sandbox and charged to the saved wallet, and held purchases are paid from the same wallet once approved, with no popup. The rest of the deployment stays in replay. It is off by default, a run's budget is capped (`SANDBOX_RUN_BUDGET_CAP`, 2500 USD), and runs are limited to 3 an hour per visitor and `SANDBOX_RUNS_PER_HOUR` overall. Test money only, but it is your sandbox: leave it off on a public deployment unless you want visitors spending it. The payout step stays scripted in a sandbox run.

## What is live and what is simulated

| Stage | State |
|---|---|
| 1 Delegate, 3 Govern, 4 Settle | Real code. **Live against the PayPal sandbox**: Orders v2, including saved-wallet (vault) capture with no popup, and the PayPal JS SDK approval button for orders that need a person. |
| 2 Discover | Real code. **Live against Channel3** (`/v1/search`), with a labelled retailer return-policy table because Channel3 does not return return terms. |
| 2 Negotiate | Real protocol, **simulated sellers**: deterministic concession policies, not merchants or LLMs. |
| 5 Verify, 6 Reconcile, 7 Payout, 10 Learn | Real code, **scripted inputs** in replay. Delivery proof can be recorded live. The Payouts v1 call has been run against the sandbox. Mission Control has a **Run post-purchase checks** button on each settled purchase: verify delivery, reconcile the invoice, a spoofed resubmission flagged, a payout the gates refuse, then the payout released. The carrier report and vendor invoices in that sequence are scripted, and in live mode the sandbox payout is not fired from the button. |
| 7 Webhooks | Real endpoint and raw-body verification, unit-tested. Not yet checked against a real PayPal sandbox event. |
| 8 Defend | Reads **real sandbox disputes** and answers through PayPal's dispute actions. The multipart `provide-evidence` upload is verified against the replay gateway, not yet against a live case. |
| 9 Observe | Real. AG Studio over the ledger (`Purchases` and `Agent Activity` pages), with a seeded history of past purchases built through the same step functions. |
| 9 Observe, PayPal pages | Real code, **two data modes**. The Command Center's Revenue, Receivables, Cash and Catalogue pages read the merchant's own PayPal account (invoices, payments, catalog products, billing plans, Transaction Search for the last 31 days, payouts, balances) through `GET /api/studio/paypal`, and join `Transactions.capture_id` to `PayPal Transactions.id` so an agent purchase links directly to its PayPal settlement. **Live** (`REPLAY_MODE=false` with sandbox keys) reads the sandbox account itself (falls back to the replay fixture only when PayPal answers 403, e.g. Transaction Search is not enabled on the sandbox app; any other failure is shown as an error, never as fixture data); the public replay demo serves a small **fixed fixture** of PayPal-shaped responses (fictional merchant, dated 2026-11-05) through the same transformation code. The replay fixture includes purchase captures with the seeded history's `CAP-0000xx` IDs, so the agent-to-PayPal join works in replay too; it is a fixture, not your sandbox data. The live read was run against the real sandbox account on 2026-11-12 and succeeded: 94 account-ledger transactions, 7 payouts and 2 balances (the account has no invoices, products or billing plans, so Revenue, Receivables and Catalogue are empty live). Joined to the real ledger, the three sandbox captures matched their PayPal transactions exactly. A **Reconciliation** page checks each captured agent purchase against the PayPal account ledger (`GET /api/studio/reconciliation`): Matched, Amount mismatch, Pending (Transaction Search can lag), Outside window (older than its 31 days), Unsettled, or Not decided by agent. Seeded-history and replay purchases are labelled **Simulated**, because no PayPal object exists for them; a real capture from a sandbox run on a replay deployment is labelled **Sandbox capture** (the fixture cannot contain it), and matches normally when the PayPal read is live. |

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
| **AG Grid / AG Studio** | The Command Center is a seven-page AG Studio report grouped under **Agent** (`Purchases`, `Agent Activity`, `Reconciliation`) and **PayPal account** (`Revenue`, `Receivables`, `Cash`, `Catalogue`): spend, savings by vendor, firewall routes and latency, human escalations, dispute outcomes beside supplier trust, and PayPal account reporting joined to agent captures via `capture_id`. Clicking a row opens its sealed lineage or PayPal detail drawer. A **Live** feed applies new and changed purchases to Studio as data transactions (pause it, or set 2, 5 or 10 seconds), so a run you approve in Mission Control appears without reloading. It covers the purchase pages; the PayPal pages update on Refresh. A mandate v1 → v2 diff sits beside it. The Studio assistant runs on **Claude Haiku 5.5** through an adapter we wrote for Studio's `AgLlmAdapter` contract, with the key held server-side. |
| **Channel3** | Live product search for the retail baseline and candidate sellers. |
| **Render** | One Docker web service deployed from `render.yaml` at [https://pactguard-ai.onrender.com](https://pactguard-ai.onrender.com) serving the FastAPI backend and built React frontend together. |
| **APIMatic** | Used after the fact, as an independent check, not while writing the code. We ran our real Orders v2 create-order payloads (two purchase units and the saved-wallet payment source) through the models of APIMatic's generated [`paypal-server-sdk`](https://pypi.org/project/paypal-server-sdk/) 2.4.0: nothing we send is unknown to the SDK or altered by it, the required fields are present, and an injected misspelt field is caught. Our Transaction Search query parameters also match the SDK's. That SDK has no Invoicing, Payouts or Disputes models, so those payloads were **not** validated this way. Re-run it with [`backend/scripts/apimatic_check.py`](backend/scripts/apimatic_check.py). We also installed APIMatic's PayPal Context Plugin on 2026-11-12, after the integration code was written, so it did not guide that code. |
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

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): the loop, the shared primitives (ledger, lineage, request IDs, gate tokens, money), the hand-off guard table with the test behind each guard, the API map and security notes.
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md): modes, every environment variable, local development, Render deployment, real webhooks, the sandbox run button, how to verify a deployment, and known quirks.

## Credits

The Command Center's PayPal pages (Revenue, Receivables, Cash, Catalogue), their data sources and the PayPal account tables behind them are adapted from the PayPal AI Hackathon's AG Grid boilerplate, [paypaldev/hackathon-paypal-ag-grid-boilerplate](https://github.com/paypaldev/hackathon-paypal-ag-grid-boilerplate) (`lib/paypal.ts`, `lib/dashboard-data.ts`, `app/dashboard/studio/`). The boilerplate is ported to Python and React here, and its repository carries no licence file, so we use it as the hackathon's provided starting point.

## Known Limitations

- **Simulated parts:** sellers in negotiation are deterministic policies, not merchants; the carrier report and vendor invoices in the post-purchase sequence are scripted; the payout stays scripted in a sandbox run.
- **Not yet verified live:** webhook handling against a real PayPal event, and the multipart dispute-evidence upload against a live case. Both are unit-tested against the replay gateway.
- **Live feed:** it adds and updates purchases in the Studio tables only; the PayPal pages update on Refresh. The rows endpoint returns the latest run, so an earlier run's rows stay until you reload.
- **Studio console message:** with AG Studio 3.1.0, switching onto Revenue or Receivables logs one harmless message (see [`docs/OPERATIONS.md`](docs/OPERATIONS.md)).

- **Held-out prompt injection paraphrasing:** The prompt-injection firewall currently relies on regex tripwires. While it catches 100% of direct phrasings and known evasion attacks with sub-millisecond deterministic latency, novel paraphrases can evade regex detection. Because untrusted text can only escalate to a human or block (it can never force an auto-settle), this cannot cause an unauthorized spend, but an escalate-only structured LLM classifier is planned to close the paraphrase gap.
- **Budget holds on sealed orders:** an order that is sealed but not yet captured counts against the mandate budget, so two approvals cannot overspend it. If a buyer closes the PayPal popup, that hold expires after 30 minutes (`SEAL_HOLD`); until then it can block a later purchase in the same run. Capture re-checks the budget, so an order whose hold lapsed cannot be captured over budget. A captured order is spend for good.
- **Ledger truncation needs an anchor kept elsewhere:** the hash chain and the database triggers catch edits and deletions in the middle. Every append is also signed with `GATE_SECRET` (`checkpoints` table), which catches a truncation that leaves that table alone; someone who can alter the database file can alter both. Fetch `GET /api/ledger/checkpoint` and keep it off the machine, then pass it to `GET /api/ledger/verify` to detect any rewrite or truncation behind it, however far the ledger has grown since. Rotating `GATE_SECRET` makes old checkpoints unverifiable, not the chain broken.
- **Assistant rate limit:** requests are limited per client (40 a minute), keyed on proxy headers a caller can set, and also by a global ceiling of 30 a minute across all clients. A caller rotating the header can therefore not exceed the ceiling, but heavy shared use could hit it.
