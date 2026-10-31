# Section 9: Implementation Framework — The Unified Full Loop

This is the engineering companion to the strategy docs (01–08). It turns the five ideas into **one closed loop** and maps every stage, hand-off guard and demo moment to code and a test that already exist in `backend/`.

> **Status (2026-10-29):** All ten stages are implemented as a backend skeleton. The full demo arc runs end-to-end in **replay mode** (deterministic stand-ins for PayPal, Channel3 and the LLM). `29` tests pass, and each hand-off guard has its own test. The next step is to swap replay for live sandboxes. The open blockers are listed in [§7 Readiness](#7-readiness-analysis). The phased plan for getting from here to submission is in [10-execution-plan.md](10-execution-plan.md).

---

## 1. The loop

**Delegate → Buy → Pay → Deliver → Get paid / pay out → Defend → Learn → tighter mandate.**

| Stage | Absorbs | Agent role | Module | Scope tier | Built |
|---|---|---|---|---|---|
| 1 Delegate | PactGuard | Mandate + digest = lineage root | `app/stages/s01_delegate.py` | **Real** | ✅ |
| 2 Discover | PactGuard | Channel3 product graph, retail baseline | `app/stages/s02_discover.py`, `app/integrations/channel3.py` | **Real** | ✅ replay / ⚠️ live shape unverified |
| 2 Negotiate | PactGuard | Buyer vs N sellers, 3 turns, schema-gated, CANO | `app/stages/s02_negotiate.py` | **Real** | ✅ |
| 3 Govern | PactGuard | 4-factor Mandate Firewall + approval | `app/stages/s03_govern.py` | **Real** | ✅ |
| 4 Settle & Seal | PactGuard | Orders v2 + Decide-and-Prove seal, draft-first invoice | `app/stages/s04_settle.py`, `app/core/money.py` | **Real** | ✅ replay / sandbox client written |
| 5 Deliver & Verify | ChronoPay | Deliverable verifier, tranche reschedule | `app/stages/s05_verify.py` | Mock (scripted) | ✅ |
| 6 Reconcile | HaystackAP | Invoice forensics: 3-way match, spoof, duplicates | `app/stages/s06_reconcile.py` | Mock (one flagged invoice) | ✅ |
| 7 Pay out & Collect | ChronoPay | Payouts v1, gross-to-net, webhooks, nudges | `app/stages/s07_payout.py` | Mock (single payout) | ✅ |
| 8 Defend | AegisPay | Evidence from ledger → PDF → `provide-evidence` | `app/stages/s08_defend.py` | **Thin but live** | ✅ replay |
| 9 Observe | PayPulse / AG Studio | Row data + KPIs for AG Grid / Studio | `app/stages/s09_observe.py`, `GET /api/studio/rows` | **Real** | ✅ data / ❌ UI |
| 10 Learn | Feedback | Supplier trust, threshold calibration, new mandate version | `app/stages/s10_learn.py` | Mock (rule-based before/after) | ✅ |

The demo arc is wired in `app/orchestrator.py::run_demo` and exposed at `POST /api/demo/run`.

### What the demo arc produces today (replay)

```text
1  mandate_registered   PG-211e…  (digest = lineage root)
2  discovered           webcams baseline $94.00
2  negotiated           Northwind @ $340 (-12.6% vs baseline); Globex dropped by schema gate;
                        reservations {Northwind: COMMITTED, Contoso: CANCELLED}
3  firewall             webcams  -> AUTO_SETTLE      (0.2 ms)
3  firewall             monitors -> HUMAN_APPROVAL   (1020 > 300 threshold)
3  firewall             $900 payout -> BLOCKED       (injection + agent-initiated payout + not allowlisted)
4  guard                NOT_AUTHORIZED: settle attempted before approval
4  settled              webcams $118, monitors $1020 (after 1-click approval)
5  verified             webcams FAIL (tracking LOST), monitors PASS
6  reconciled           NW-1001 CLEAN; "NW 1001" resubmitted -> DUPLICATE + PAYEE_MISMATCH
7  guard                GATE_TOKEN_INVALID: payout without verified delivery
7  payout_released      net $999.35 after fees; duplicate webhook ignored
8  disputes             triage by deadline; NOT_AS_DESCRIBED odds 0.95, NOT_RECEIVED odds 0.15
9  kpis                 1 auto / 1 approved / 1 blocked, $217 saved, 1 won / 1 lost
10 calibrated           Contoso removed (trust 0.4); auto_threshold 300 -> 225  => mandate v2
   ledger verified      chain intact, 21 entries
```

---

## 2. Cross-cutting primitives (the glue)

These four primitives are what make the system one product rather than five demos. They live in `app/core/`.

| Primitive | File | What it guarantees |
|---|---|---|
| **Sealed Evidence Ledger** | `core/ledger.py` | Append-only and hash-chained. SQLite triggers refuse `UPDATE` and `DELETE`, and `verify()` finds the first tampered row. Stage 4 writes the seal, stage 5 writes the delivery proof, stage 8 reads both. |
| **Lineage thread** | `core/lineage.py` | `mandate digest → PG-<16 hex>` is the mandate lineage, and `PG-….<10 hex>` is each transaction's lineage. It rides in Orders `custom_id` and `reference_id`, the invoice `detail.reference`, the payout `sender_batch_id`, every webhook lookup and every ledger row. This is the fix for Issue 113, where lineage is lost. |
| **Deterministic request IDs** | `core/lineage.py::request_id` | `PayPal-Request-Id = f(lineage, stage, operation, subject)`. A retry derives the same ID, so PayPal returns the original result. Different operations never collide. |
| **Gate tokens** | `core/gates.py` | HMAC tokens bound to one lineage and one subject: `APPROVED` (3→4), `VERIFIED` (5→7) and `RECONCILED` (6→7). They can't be forged or replayed across transactions. |
| **Penny-exact money** | `core/money.py` | `Decimal` throughout. Tax is computed per unit and then multiplied, so `item_total`, `tax_total` and `amount` satisfy PayPal's identities by construction, and the result is asserted again before sending. |
| **Schema gate** | `stages/s02_negotiate.py::schema_gate` + `domain/models.py::Offer` (`extra="forbid"`) | Untrusted output from sellers or the LLM only moves forward once it parses into a typed contract. |
| **Replay gateways** | `integrations/paypal.py::ReplayPayPal`, `integrations/channel3.py::ReplayChannel3` | Same interface as live. They honour request-id idempotency and can inject the failures the guards defend against. `REPLAY_MODE=true` keeps the demo safe from sandbox outages. |

**Design rule: money decisions are deterministic, and the LLM only drafts language.** `integrations/llm.py` (Claude, `claude-opus-5-5`, structured outputs, server-side refusal fallback) is optional. Anything it returns passes the same schema gate as a seller would. Judges can therefore see *why* each route was chosen, and the demo can't be derailed by a model's phrasing.

---

## 3. Hand-off guard matrix

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

## 4. The improvements we are highlighting

These are the gaps in PayPal's agent toolkit and agentic-commerce practice that the loop closes, and where each one shows up in the demo.

| # | Gap (from docs 03 / 07) | Our improvement | Where it shows on screen |
|---|---|---|---|
| 1 | Toolkit has **no spend cap** before `pay_order` | 4-factor firewall in front of *every* money movement, orders and payouts alike | Stage 3 route cards + blocked injection |
| 2 | **No idempotency** discipline | Lineage-derived `PayPal-Request-Id`, plus `sender_batch_id` for payouts | Retry button → same order ID |
| 3 | **Prompt injection** can trigger spend | Untrusted text scanned. Agent-initiated payouts are a hard `warrant` failure | "Simulate attack" → BLOCKED in <1 ms |
| 4 | Agent negotiation **over-concedes / loops / double-commits** | 3-turn protocol, schema gate, reserve-then-commit | Negotiation arena: malformed seller dropped, runner-up cancelled |
| 5 | **AMOUNT_MISMATCH** / false "captured" / live-as-draft | Penny-exact builder. Trust only `captures[].status`. Draft-first invoicing | Pre-flight check row in the settlement drawer |
| 6 | Disputes are **surrender-only** (`accept_dispute_claim`) | Evidence assembled from records sealed *before* the dispute, then sent as a PDF + `provide-evidence` | Dispute card: win odds, sealed terms hash, chain verified ✅ |
| 7 | **Lineage lost** across order → invoice → payout → dispute (Issue 113) | One lineage ID on every call and ledger row | Click any row → full lineage timeline |
| 8 | No **payout safety** | Payout requires both VERIFIED and RECONCILED tokens | Payout blocked, then released |
| 9 | Static dashboards | Studio rows/KPIs designed for AG Studio custom widgets | Stage 9 |
| 10 | Rules never improve | Outcomes → supplier trust → mandate v2 (with `parent_digest`) | Before/after mandate diff |

---

## 5. Layout

```text
backend/
├── app/
│   ├── core/            canonical.py  ledger.py  lineage.py  gates.py  money.py  errors.py
│   ├── domain/          models.py       (Mandate, Need, Offer, Proposal, Decision, DeliveryReport, VendorInvoice, Dispute)
│   ├── integrations/    paypal.py (Replay + Sandbox)  channel3.py (Replay + Live*)  llm.py (Claude, optional)
│   ├── stages/          s01_delegate … s10_learn
│   ├── orchestrator.py  Runtime + run_demo (the 3-minute arc)
│   ├── api.py           /api/demo/run  /api/ledger  /api/ledger/verify  /api/studio/rows
│   └── main.py
└── tests/               test_handoff_guards.py  test_ledger_and_firewall.py  test_health.py
frontend/                Vite + React + TS + Tailwind starter (UI not built yet)
```

How to run:

```bash
make setup
```

```bash
make test
```

```bash
make backend
```

```bash
curl -s -X POST localhost:8000/api/demo/run
```

---

## 6. What is left, by tier

| Tier | Stage | Remaining work |
|---|---|---|
| **Must be real** | 1–4 | Switch `REPLAY_MODE=false` and run against PayPal sandbox. Add the JS SDK approve button. Capture after the buyer approves (see blocker B-3). Run against the live Channel3 adapter. |
| **Must be real** | 9 | AG Studio UI: grid over `/api/studio/rows`, 3 custom widgets (savings vs baseline, firewall routes, dispute win-rate), Studio Agent NL queries. |
| **Must be real** | UI | Negotiation arena, firewall drawer (Auto / Approval / Blocked cards + "simulate attack"), lineage timeline, dispute card. |
| **Thin but live** | 8 | One real sandbox dispute answered with `provide-evidence` from the ledger (see blocker B-4). |
| Mock / stretch | 5, 6, 7, 10 | Already scripted. Stretch goals: real Payouts sandbox call, real webhook endpoint with verification, LLM-written dispute narrative. |
| Cut | — | Bryntum Gantt (`s05_verify.reschedule` is the Gantt-lite stand-in). |

---

## 7. Readiness analysis

### ✅ Ready
- Dev environment: Python venv, FastAPI, Vite/React/Tailwind, Makefile, `.env.example`.
- All 10 stages and the guards, runnable offline with deterministic output for rehearsing the video.
- Sandbox PayPal client written for Orders v2, Invoicing v2, Payouts v1, Disputes `provide-evidence` and webhook verification, with OAuth token caching. **It has not yet been exercised against the sandbox.**

### 🟥 Blockers — need a human or an account
| ID | Blocker | Owner action |
|---|---|---|
| B-1 | **PayPal sandbox credentials** | Create a sandbox REST app. Put `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` and `PAYPAL_WEBHOOK_ID` in `.env`. Create a sandbox business account and a sandbox personal (buyer) account. |
| B-2 | **Payouts in sandbox** | Payouts must be enabled for the sandbox business account. Check this on day 1, because a 403 there kills stage 7 live. |
| B-3 | **Order approval flow** | A real sandbox order can't be captured until a buyer approves it. Replay auto-approves. The frontend needs the PayPal JS SDK button (`createOrder` → our `/prepare`, `onApprove` → our `/capture`). Endpoints still to add. |
| B-4 | **Real sandbox dispute** | A sandbox dispute has to be opened from the sandbox buyer account in the Resolution Center, and evidence can only be submitted in certain dispute states. Open one **early**, since it can take time to reach a state that accepts evidence. Replay is the fallback for the video. |
| B-5 | **Channel3 API shape** | The live adapter's path, auth header and field names are **placeholders**. `docs.trychannel3.com` was not reachable from the build sandbox. Confirm against the docs and redeem `PAYPAL-HACKATHON-2026`. Only `LiveChannel3` changes. |
| B-6 | **AG Studio / Studio Agent Framework** | Start the trial and get the licence key and package names. Nothing AG Grid-related is installed yet. |
| B-7 | **APIMatic Context Plugin, Render** | Set up accounts. These are not touched by the code yet. |
| B-8 | **LLM key** | Optional for the demo (replay works without it). Set `ANTHROPIC_API_KEY` for LLM-drafted seller messages and dispute narratives. |

### 🟧 Decisions to make before building the UI
1. **Who the merchant is in stage 8.** In stages 2–4 we are the *buyer*. Disputes are filed by a buyer *against a seller*. To defend a dispute we must be the seller. Pick one story and use it in the pitch. A suggested story: *PactGuard runs procurement for a business that also resells or bills its own customers.* The customer disputes, the business defends from the sealed record, and the loss is attributed back to the supplier that sourced the item. The code already attributes outcomes to `seller_id`.
2. **Funds flow for stage 7.** The payout releases supplier funds after verification, which implies the platform collects first (escrow-style). This is fine for the demo, but say so explicitly. A real marketplace would need PayPal's multiparty or partner onboarding.
3. **Auto vs review-first default** (blocker B1 in the diagram). The code supports both through `Mandate.mode`. The demo uses `auto` with a $300 threshold.

### 📝 Decisions recorded (Phase 0, 2026-10-31)

These adopt the recommendations in `docs/10-execution-plan.md` §4 Phase 0. They are **proposed defaults, pending team confirmation**. Change them here if the team disagrees.

| ID | Decision | Status |
|---|---|---|
| D-1 | Stage 8 merchant: the business buys through PactGuard and resells or bills its own customers. A customer disputes, the business defends from the sealed record, and the loss counts against the supplier's trust score. | Proposed |
| D-2 | Stage 7 funds flow: escrow-style (the platform collects first, releases after verification). The pitch says so, and notes production would use PayPal multiparty. | Proposed |
| D-3 | Default mandate mode: `auto` with a $300 threshold. `review_first` is shown as a toggle. | Proposed |
| D-4 | Dispute evidence: draft, then 1-click submit. Auto-submit is a mandate toggle. | Proposed |

### ✅ Phase 0 status

| Item | State |
|---|---|
| `make setup` / `make test` | Done. 29 passing. |
| Preflight script | `scripts/phase0_check.py` checks B-1, B-2, B-4, B-5, B-8 and the source list. Verified only to the point of skipping cleanly with no credentials. |
| B-1 … B-9 accounts, dispute, wallet test | **Open. Needs the team.** |
| Source check (arXiv IDs in doc 02, links in doc 03) | **Open.** The build sandbox cannot reach arxiv.org. Run `backend/.venv/bin/python scripts/phase0_check.py sources` from a machine with internet access. |

### ⚠️ Corrections to earlier docs
- README / docs 07–08 list `gpt-4o` and `claude-3-5-sonnet`, which are outdated. The LLM layer now targets `claude-opus-5-5` (configurable through `LLM_MODEL`).
- The plan is framed as a "36-hour sprint", but the deadline is **12 Nov 2026, ~14 days away**. That leaves room to move stages 7 and 8 from mock to live. The scope cut above is the floor, not the ceiling.
- The arXiv IDs cited in docs 02/07 (e.g. `2610.29216`) were **not verified** here. Check them before they appear in the pitch or video.

---

## 8. Suggested split (3 people)

| Person | Week 1 | Week 2 |
|---|---|---|
| **A — Payments** | B-1/B-2/B-3: live sandbox for stages 1–4. Add `/prepare` and `/capture` endpoints. Run the guard tests against the sandbox. | B-4 live dispute + `provide-evidence`. Webhook endpoint. Live payout. |
| **B — Frontend** | Negotiation arena, firewall drawer, JS SDK approve button, lineage timeline | Dispute card, mandate before/after diff, demo polish |
| **C — Data / Sponsors** | B-5 Channel3 live. B-6 AG Studio grid over `/api/studio/rows` | 3 custom Studio widgets + NL queries. APIMatic. Render deploy. Video. |

Rule for everyone: **a new guard ships with a test in `tests/test_handoff_guards.py`, and the demo must stay green with `REPLAY_MODE=true`.**
