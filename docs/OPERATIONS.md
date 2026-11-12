# Operations

Running, deploying and checking PactGuard AI. Architecture is in [ARCHITECTURE.md](ARCHITECTURE.md); what is live versus simulated is in the [README](../README.md).

## Modes

| Mode | How | What it does |
|---|---|---|
| **Replay** (default) | `REPLAY_MODE=true` | PayPal, Channel3 and the LLM are deterministic stand-ins. Nothing leaves the process, so it never depends on sandbox uptime. The public demo runs this way. |
| **Live sandbox** | `REPLAY_MODE=false` with `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` | Real orders, captures, invoices, payouts and disputes against `api-m.sandbox.paypal.com`. The Command Center reads the real sandbox account. |
| **Sandbox run button** | `ALLOW_SANDBOX_RUNS=true` plus the PayPal keys and `PAYPAL_VAULT_ID` | A replay deployment offers one real run per click. See below. |

## Environment variables

Copy `.env.example` to `.env` (never commit it). The browser only ever sees `VITE_*` variables, and the only one is the AG Studio licence key.

| Variable | Purpose |
|---|---|
| `REPLAY_MODE` | `true` for replay, `false` for the live sandbox |
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_BASE_URL` | Sandbox app credentials |
| `PAYPAL_VAULT_ID` | Saved wallet for popup-free capture |
| `PAYPAL_WEBHOOK_ID` | Webhook id, for signature verification of real events |
| `CHANNEL3_API_KEY`, `CHANNEL3_BASE_URL` | Live product search |
| `ANTHROPIC_API_KEY`, `LLM_MODEL` | Studio assistant and dispute-draft wording (default `claude-haiku-5-5`) |
| `GATE_SECRET` | Signs gate tokens and ledger checkpoints. A placeholder is refused outside replay mode. Changing it makes old checkpoints unverifiable, not the chain broken |
| `LEDGER_PATH` | SQLite file for live runs (replay runs are in memory) |
| `RETURN_ADDRESS_*` | Returns address shown to the buyer in refund-on-return offers; required in live mode |
| `ALLOW_SANDBOX_RUNS`, `SANDBOX_RUN_BUDGET_CAP`, `SANDBOX_RUNS_PER_HOUR` | The sandbox run button and its limits |
| `CORS_ORIGINS`, `FRONTEND_DIST` | Cross-origin dev servers; folder of the built frontend to serve |
| `VITE_AG_STUDIO_LICENSE` (in `frontend/.env.local`) | AG Studio licence key. Unset runs in watermark mode |

## Local development

```bash
make setup      # venv, npm install, copies .env.example to .env
make backend    # API on :8000
make frontend   # UI on :5173 (proxies /api to the backend; set API_TARGET to change it)
make test       # backend tests (191)
make serve      # builds the frontend and serves both from one process on :8000
```

Lint and build: `cd backend && ruff check . && ruff format --check .`, `cd frontend && npx oxlint && npm run build`. CI runs the same.

Evaluations: `cd backend && python -m eval.run_all` rewrites `eval/RESULTS.md`.

If you switch branches or upgrade `ag-studio`, restart the Vite dev server: it caches the old pre-bundled package.

## Deploying to Render

`render.yaml` and the `Dockerfile` define one web service that serves the API and the built frontend from one process, with a single worker (run sessions live in memory). Create it from the Blueprint, fill in the secrets Render asks for, and keep `REPLAY_MODE=true` for the public URL. The disk is ephemeral, so the ledger resets on restart and the seeded history is rebuilt on demand. A `keep_warm` GitHub Action pings `/api/health` so the service stays awake.

## Real PayPal webhooks

Register `https://<service>/api/webhooks/paypal` as a webhook in the sandbox app, set `PAYPAL_WEBHOOK_ID`, then fire an event from PayPal's webhook simulator. The endpoint verifies against the raw bytes, de-duplicates by event id and seals the event in the ledger. This path is unit-tested but has not yet been checked against a real PayPal event.

## The sandbox run button

Set `ALLOW_SANDBOX_RUNS=true`, the PayPal client id and secret, and `PAYPAL_VAULT_ID`, and Mission Control shows **Run in PayPal sandbox** under the mandate, behind a confirmation. That one run creates real orders and captures in the project's sandbox, charged to the saved wallet; held purchases are paid from the same wallet after approval, with no popup. The rest of the deployment stays in replay.

Guards: off by default; a run's budget is capped (`SANDBOX_RUN_BUDGET_CAP`, 2500 USD); 3 runs an hour per visitor and `SANDBOX_RUNS_PER_HOUR` overall; the vault id never reaches the browser or the ledger. It is test money but it is your sandbox, so leave it off on a public deployment unless you want visitors spending it. Payout stays scripted in a sandbox run. On a replay deployment the Command Center reads the fixed PayPal fixture, so a sandbox run's captures appear on the Reconciliation page as **Sandbox capture** (real, but not matchable there); check them in the sandbox account's Activity, or run live to see them matched.

## Verifying a deployment

1. `GET /api/health` returns `status: ok`, the mode and whether a sandbox run is offered.
2. Press **Run agent**, approve the held purchase, run the post-purchase checks, simulate the attack and check the ledger says "chain verified".
3. Open **Command Center**: seven pages render and the Live chip is green.
4. `GET /api/ledger/verify` returns `chain_ok: true`; `GET /api/studio/history/verify` verifies the seeded history.

## Known quirks

- **Studio console message on page switch.** With AG Studio 3.1.0, moving from Purchases onto Revenue or Receivables logs once: "This query reads sources that no relationship connects…". Those two pages carry page-level filters on the invoices table, and during the switch Studio runs the page being left (which reads the unrelated `transactions` table) under the new filters. A deep link does not trigger it and nothing renders wrongly.
- **Transaction Search** needs enabling on the sandbox app (a 403 otherwise, which falls back to the replay fixture) and can lag new payments by a few hours; vaulted captures appear under event code `T0003`, checkout captures under `T0006`.
- **Replay fixture dates** are fixed at 2026-11-05; the live read reflects the real account.
