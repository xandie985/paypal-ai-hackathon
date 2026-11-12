# Architecture

How PactGuard AI is built and why. For what is live versus simulated, the evaluation numbers and the known limits, see the [README](../README.md). For environment variables, deployment and the live sandbox, see [OPERATIONS.md](OPERATIONS.md).

## 1. The loop

**Delegate → Discover → Negotiate → Govern → Settle and seal → Verify → Reconcile → Pay out → Defend → Learn**

Each stage is one module in `backend/app/stages/` (`s01_delegate` … `s10_learn`), written as functions over the evidence ledger. `backend/app/runs.py` wraps them in run sessions that a UI can pause at a human-approval gate, and `backend/app/orchestrator.py` holds the runtime (ledger, gateways, budget accounting).

Money decisions are deterministic. The only LLM in the system drafts language (dispute responses, the Studio assistant); anything it returns passes the same schema gate as seller text would.

## 2. Cross-cutting primitives

These four primitives are what make the system one product rather than five demos. They live in `app/core/`.

| Primitive | File | What it guarantees |
|---|---|---|
| **Sealed Evidence Ledger** | `core/ledger.py` | Append-only and hash-chained. SQLite triggers refuse `UPDATE` and `DELETE`, and `verify()` finds the first tampered row. Stage 4 writes the seal, stage 5 writes the delivery proof, stage 8 reads both. |
| **Lineage thread** | `core/lineage.py` | `mandate digest → PG-<16 hex>` is the mandate lineage, and `PG-….<10 hex>` is each transaction's lineage. It rides in Orders `custom_id` and `reference_id`, the invoice `detail.reference`, the payout `sender_batch_id`, every webhook lookup and every ledger row. One ID follows a purchase from order to dispute, so nothing has to be matched by guesswork. |
| **Deterministic request IDs** | `core/lineage.py::request_id` | `PayPal-Request-Id = f(lineage, stage, operation, subject)`. A retry derives the same ID, so PayPal returns the original result. Different operations never collide. |
| **Gate tokens** | `core/gates.py` | HMAC tokens bound to one lineage and one subject: `APPROVED` (3→4), `VERIFIED` (5→7) and `RECONCILED` (6→7). They can't be forged or replayed across transactions. |
| **Penny-exact money** | `core/money.py` | `Decimal` throughout. Tax is computed per unit and then multiplied, so `item_total`, `tax_total` and `amount` satisfy PayPal's identities by construction, and the result is asserted again before sending. |
| **Schema gate** | `stages/s02_negotiate.py::schema_gate` + `domain/models.py::Offer` (`extra="forbid"`) | Untrusted output from sellers or the LLM only moves forward once it parses into a typed contract. |
| **Replay gateways** | `integrations/paypal.py::ReplayPayPal`, `integrations/channel3.py::ReplayChannel3` | Same interface as live. They honour request-id idempotency and can inject the failures the guards defend against. `REPLAY_MODE=true` keeps the demo safe from sandbox outages. |

**Design rule: money decisions are deterministic, and the LLM only drafts language.** `integrations/llm.py` (Claude, `claude-haiku-5-5`, structured outputs, server-side refusal fallback) is optional. Anything it returns passes the same schema gate as a seller would. Judges can therefore see *why* each route was chosen, and the demo can't be derailed by a model's phrasing.

---

## 3. Hand-off guards

This is where the loop is most likely to break, and how each break is stopped. Every row has a test in `backend/tests/`.

| Hand-off | Failure | Guard (code) | Test |
|---|---|---|---|
| 2 → 3 | Two sellers both "accept" | `ReservationBook.commit` raises `DoubleCommitment`. Runner-ups are `CANCELLED` | `test_only_one_seller_can_be_committed` |
| 2 → 3 | Bad JSON, extra fields, price walk-backs, endless loops | `schema_gate` drops the seller. `MAX_TURNS = 3` | `test_schema_gate_drops_bad_json_and_price_walkbacks`, `test_negotiation_is_bounded_and_commits_exactly_one` |
| 3 → 4 | Retry double-charges | Digest-derived `PayPal-Request-Id` on create and capture | `test_retry_with_same_request_id_does_not_double_charge`, `test_request_ids_are_deterministic_and_operation_scoped` |
| 3 → 4 | Settle without approval, or with a forged approval | `prepare_order` requires `AUTO_SETTLE` or a valid `APPROVED` token for *this* decision digest | `test_human_approval_route_needs_a_valid_approval_token` |
| 3 → 4 | `AMOUNT_MISMATCH` from rounding | `build_purchase_unit` + `assert_breakdown_consistent` | `test_tax_rounding_is_penny_exact_and_mismatch_is_caught` |
| 4 → 5 | Seal missing, so no evidence later | Seal write failure raises `SealWriteFailed`. `capture` refuses without a seal (`SealMissing`) | `test_seal_write_failure_blocks_capture` |
| 4 | False "captured" | Only `captures[0].status == COMPLETED` counts. Anything else raises `NotCaptured` | `test_pending_capture_is_not_reported_as_captured` |
| 4 | Live invoice treated as a draft | `issue_invoice` checks for `DRAFT` and the expected total before `send` | `test_invoice_that_comes_back_live_is_not_sent` |
| 5 → 7 | Pay out before delivery is verified | `release_payout` requires a `VERIFIED` token. LATE or FAIL mints none | `test_payout_requires_verified_and_reconciled_tokens` |
| 6 → 7 | Duplicate or spoofed invoice paid | Forensics flags `DUPLICATE`, `PAYEE_MISMATCH`, `AMOUNT_MISMATCH` or `NO_DELIVERY_PROOF`. No `RECONCILED` token is minted | `test_duplicate_and_spoofed_invoices_are_flagged` |
| 7 → 8 | Webhook lost, duplicated or unverifiable | `WebhookInbox` verifies, deduplicates by event id, stores and replays | `test_webhooks_are_verified_deduplicated_and_replayable` |
| 8 → 10 | Dispute lost, nothing learned | `record_outcome` writes a WON/LOST label, and `calibrate` consumes it | `test_full_loop_demo_arc` |
| Ledger | Evidence edited after the fact | DB triggers + hash chain `verify()` | `test_ledger_rejects_update_and_delete`, `test_ledger_detects_tampering` |
| Firewall | Injection, off-allowlist vendor, budget, hidden terms, review-first | `s03_govern.evaluate` (9 parametrised cases) | `test_firewall_routes`, `test_review_first_mode_never_auto_settles`, `test_budget_counts_prior_spend` |

---

## 4. What PayPal's agent toolkit lacks, and what closes it

The gaps below are in the toolkit and in common agentic-commerce practice. Each row names what closes it and where it shows on screen.

| # | Gap | Our improvement | Where it shows on screen |
|---|---|---|---|
| 1 | Toolkit has **no spend cap** before `pay_order` | 4-factor firewall in front of *every* money movement, orders and payouts alike | Stage 3 route cards + blocked injection |
| 2 | **No idempotency** discipline | Lineage-derived `PayPal-Request-Id`, plus `sender_batch_id` for payouts | Retry button → same order ID |
| 3 | **Prompt injection** can trigger spend | Untrusted text scanned. Agent-initiated payouts are a hard `warrant` failure | "Simulate attack" → BLOCKED in <1 ms |
| 4 | Agent negotiation **over-concedes / loops / double-commits** | 3-turn protocol, schema gate, reserve-then-commit | Negotiation arena: malformed seller dropped, runner-up cancelled |
| 5 | **AMOUNT_MISMATCH** / false "captured" / live-as-draft | Penny-exact builder. Trust only `captures[].status`. Draft-first invoicing | Pre-flight check row in the settlement drawer |
| 6 | Disputes are **surrender-only** (`accept_dispute_claim`) | Evidence assembled from records sealed *before* the dispute, then sent as a PDF + `provide-evidence` | Dispute card: win odds, sealed terms hash, chain verified ✅ |
| 7 | **Lineage lost** across order → invoice → payout → dispute  | One lineage ID on every call and ledger row | Click any row → full lineage timeline |
| 8 | No **payout safety** | Payout requires both VERIFIED and RECONCILED tokens | Payout blocked, then released |
| 9 | Static dashboards | Studio rows/KPIs designed for AG Studio custom widgets | Stage 9 |
| 10 | Rules never improve | Outcomes → supplier trust → mandate v2 (with `parent_digest`) | Before/after mandate diff |

---

## 5. Layout

```text
backend/
  app/
    core/           canonical.py ledger.py lineage.py gates.py money.py errors.py
    domain/         models.py   (Mandate, Need, Offer, Proposal, Decision, DeliveryReport, VendorInvoice, Dispute)
    integrations/   paypal.py (Replay + Sandbox)   channel3.py (Replay + Live)   llm.py (Claude, optional)
    stages/         s01_delegate … s10_learn
    orchestrator.py Runtime: ledger, gateways, committed-spend accounting (seals expire after 30 minutes)
    runs.py         run sessions: the loop behind step functions a UI can pause, plus post-purchase and sandbox runs
    api.py          REST and SSE, webhooks, disputes, ledger, Studio rows and lineage
    ai_proxy.py     Studio assistant proxy (key held server-side, per-client and global rate limits)
    studio_paypal.py, studio_reconcile.py   PayPal account tables and agent-to-PayPal reconciliation for the Command Center
    sandbox_gate.py  who may start a real sandbox run, and how often
    seed.py         seeded history of past purchases, built through the same step functions
  eval/             firewall, negotiation and idempotency evaluations (RESULTS.md)
  scripts/          apimatic_check.py, seed_history.py
frontend/src/
  features/         mandate, market, negotiation, deal, settle, postpurchase, dispute, ledger, webhooks, timeline, attack
  studio/           CommandCenter (AG Studio), PayPal and reconciliation report definitions, Claude adapter, theme
```

## 6. API map

| Area | Endpoints |
|---|---|
| Runs | `POST /api/runs` (optional `mandate`, `needs`, `sandbox`), `GET /api/runs/{id}`, `/events` (SSE), `/ledger`, `/calibration` |
| Decisions and orders | `POST /api/runs/{id}/decisions/{lineage}/approve`, `/reject`; `/orders/{lineage}/prepare`, `/capture`, `/retry` |
| Post-purchase | `POST /api/runs/{id}/post-purchase/{lineage}` (stages 5 to 7 with scripted inputs) |
| Firewall demo | `POST /api/runs/{id}/attack`, `POST /api/demo/run` (the whole loop in about a second) |
| Ledger | `GET /api/ledger`, `/ledger/verify`, `/ledger/checkpoint` |
| Studio | `GET /api/studio/rows`, `/lineage/{id}`, `/paypal`, `/reconciliation`, `/calibrations`, `/history/verify` |
| Disputes | `GET /api/disputes`, `/disputes/{id}`, `/brief.pdf`; `POST /draft`, `/respond`, `/simulate-resolve`, `/return-received` |
| Webhooks | `POST /api/webhooks/paypal`, `GET /api/webhooks`, `POST /api/webhooks/{event}/replay` |
| Assistant | `GET /api/ai/config`, `POST /api/ai/messages` |
| Health | `GET /api/health` (mode, whether a sandbox run is offered) |

## 7. Security notes

- **Keys stay server-side.** The only key in the browser bundle is the AG Studio licence. PayPal secrets, the vault id and the Anthropic key never leave the server, and the vault token is never written to the ledger or returned by any endpoint (tested).
- **Seal before money.** Capture refuses without a sealed order; a saved-wallet order is sealed before it is created. A failed seal write stops the charge.
- **Budget** counts captured spend plus sealed-but-uncaptured orders, and capture re-checks it.
- **Untrusted text** (seller messages, vendor invoices) can only block or escalate a route, never approve one.
- **Ledger** is append-only (database triggers), hash-chained, and each head is signed with `GATE_SECRET`. Keep a checkpoint off the machine to detect truncation (see the README).
- **Public deployment** runs in replay mode; a real sandbox run is off unless `ALLOW_SANDBOX_RUNS` is set, capped in size and rate-limited.
