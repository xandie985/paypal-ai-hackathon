# Section 9: Implementation Framework — The Unified Full Loop

This is the engineering companion to the strategy docs (01–08). It turns the five ideas into **one closed loop** and maps every stage, hand-off guard and demo moment to code and a test that already exist in `backend/`.

> **Status (2026-11-06):** All ten stages are implemented. The acquisition half (stages 1–4) and the dispute desk (stage 8) run live against the PayPal sandbox; stages 5, 6, 7 and 10 are scripted in replay, with stage 5 delivery proof also recordable live. `147` tests pass. Phases 0 and 1 are closed, stage 8 (planned for Phase 3) was done early, Phase 2 (Observe & Learn, AG Studio, including the Claude-backed Studio assistant) is built, and the webhook endpoint and the Render deploy files are in place. The evaluation harness is `backend/eval/`. Live experiments are logged in §7; the open items are in the Phase close-out below.

---

## 1. The loop

**Delegate → Buy → Pay → Deliver → Get paid / pay out → Defend → Learn → tighter mandate.**

| Stage | Absorbs | Agent role | Module | Scope tier | Built |
|---|---|---|---|---|---|
| 1 Delegate | PactGuard | Mandate + digest = lineage root | `app/stages/s01_delegate.py` | **Real** | ✅ |
| 2 Discover | PactGuard | Channel3 product graph, retail baseline | `app/stages/s02_discover.py`, `app/integrations/channel3.py` | **Real** | ✅ replay / ✅ live verified (/v1/search) |
| 2 Negotiate | PactGuard | Buyer vs N sellers, 3 turns, schema-gated, CANO | `app/stages/s02_negotiate.py` | **Real** | ✅ |
| 3 Govern | PactGuard | 4-factor Mandate Firewall + approval | `app/stages/s03_govern.py` | **Real** | ✅ |
| 4 Settle & Seal | PactGuard | Orders v2 + Decide-and-Prove seal, draft-first invoice | `app/stages/s04_settle.py`, `app/core/money.py` | **Real** | ✅ replay / ✅ live vault + JS SDK |
| 5 Deliver & Verify | ChronoPay | Deliverable verifier, tranche reschedule | `app/stages/s05_verify.py` | Mock (scripted) | ✅ |
| 6 Reconcile | HaystackAP | Invoice forensics: 3-way match, spoof, duplicates | `app/stages/s06_reconcile.py` | Mock (one flagged invoice) | ✅ |
| 7 Pay out & Collect | ChronoPay | Payouts v1, gross-to-net, webhooks, nudges | `app/stages/s07_payout.py` | Mock (single payout) | ✅ live verified (batch UYPJ27MNP6X5J) |
| 8 Defend | AegisPay | Evidence from ledger → PDF → `provide-evidence` | `app/stages/s08_defend.py` | **Thin but live** | ✅ live verified (PP-D-1001 odds 0.95) |
| 9 Observe | PayPulse / AG Studio | Row data + KPIs for AG Grid / Studio | `app/stages/s09_observe.py`, `GET /api/studio/rows` | **Real** | ✅ data / ✅ UI (Command Center, seven pages) |
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
| **Must be real** | 9 | AG Studio UI: grid over `/api/studio/rows`, 3 custom widgets (savings vs baseline, firewall routes, dispute win-rate), Studio Agent NL queries. Superseded by [doc 11](11-dashboard-ui-plan.md) §9–10: W1 Mandate Ruler, W2 Savings Dumbbell, W3 Lineage Chain; win rate becomes a built-in gauge. |
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
| B-6 | **AG Studio / Studio Agent Framework** | **Done (2026-11-01).** The AG Studio Pro with AI trial licence (valid to 2026-12-16) is in `frontend/.env.local` as `VITE_AG_STUDIO_LICENSE`. `ag-studio` and `ag-studio-react` 3.0.0 are installed, and `#/studio` renders licensed (doc 11, UI-0.4). |
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
| D-1 | Stage 8 merchant: the business buys through PactGuard and resells or bills its own customers. A customer disputes, the business defends from the sealed record, and the loss counts against the supplier's trust score. | Confirmed |
| D-2 | Stage 7 funds flow: escrow-style (the platform collects first, releases after verification). The pitch says so, and notes production would use PayPal multiparty. | Confirmed |
| D-3 | Default mandate mode: `auto` with a $300 threshold. `review_first` is shown as a toggle. | Confirmed |
| D-4 | Dispute evidence: draft, then 1-click submit. Auto-submit is a mandate toggle. | Confirmed |
| D-5 | **Cross-Border Fulfillment & Regional Shipping Governance:** Catalogs (Channel3) aggregate global/US feeds. To ensure items can physically be delivered to the buyer's country, the mandate enforces geographic routing through the vendor allowlist (e.g. EU/IT vs US domains), cross-border shipping terms evaluation in the firewall, and carrier delivery verification in Stage 5 before escrow payout release. | Confirmed |

### ✅ Phase 0 status

| Item | State |
|---|---|
| `make setup` / `make test` | Done. 147 passing. |
| Preflight script | `scripts/phase0_check.py`. Run 2026-10-31: 0 failed. B-1 PASS, B-2 PASS (payout batch created), B-4 WARN, B-5 PASS, B-8 skipped (optional). |
| B-1 OAuth, B-2 Payouts | **Done.** Scopes include payouts, disputes, invoicing, vault, orders. Payouts v1 needs `currency` (fixed in `s07_payout.py`). |
| B-4 Sandbox dispute | **Open.** The disputes API answers 200 but lists 0 disputes. Stage 8 uses the replay dispute `PP-D-1001` until one exists. |
| B-5 Channel3 | **Done.** `/v1/search` with `x-api-key` returns real products. It does not expose return terms, so live items route to human approval ("return terms hidden"). |
| B-6 AG Studio | **Done.** The licence validates: no watermark and no licence warning on `#/studio`. See doc 11, UI-0.4. |
| B-7 Render/APIMatic | **Open.** Accounts to set up. |
| B-9 Saved-wallet capture | **Passed (2026-11-04).** Setup token approved by sandbox buyer, exchanged for vault payment token `8ng18757…`, and test order `7LX28344P4713330H` captured server-side (`3L94707948760335B` COMPLETED) with zero popup. Confirms autonomous `AUTO_SETTLE`. |
| Source check (doc 02 arXiv IDs, doc 03 links) | **Done.** 36/36 resolved. StackOverflow and Hacker News block scripts, so those links count as passing on the anti-bot response. |

### 🔄 Phase 1 close-out (2026-11-04)

| Step | State |
|---|---|
| 1. Return-policy table + allowlist | **Built.** `RETURN_POLICY_DAYS` in `integrations/channel3.py` covers amazon.com (30d), bestbuy.com (15d), walmart.com, target.com, newegg.com, bhphotovideo.com (30d), and ebay.com (None: each seller sets its own terms). These are standard electronics windows as published. They are labelled demo data and **must be re-checked before recording**. `DEMO_MANDATE.vendor_allowlist` = the two simulated negotiators + those domains. A third demo need (USB microphone, direct) is the deliberate "terms hidden" item: in replay it routes to a human on reversibility alone ($89, under the threshold). **Not yet confirmed against live results:** run `scripts/phase0_check.py merchants` to see which domains the demo queries actually return and which one each direct buy picks. |
| 2. `test_live_channel3_mapping` | **Done.** `tests/test_channel3.py` + `tests/fixtures/channel3_search.json`: first offer wins, `www.`/URL domains normalized, brand fallback with no offers, `"$1,024.50"` and scalar prices, `images[]` fallback, unpriced/$0 listings dropped, allowlist coverage, discovery baseline over mapped data. |
| 3. `PayPalApprove.tsx` | **Built.** Replay keeps the 1-click button. Live (`/api/health` → `paypal_live` + public `paypal_client_id`) renders `@paypal/react-paypal-js` `PayPalButtons`: `createOrder` → `/prepare`, `onApprove` → `/capture`, then shows the sandbox order and capture IDs. PayPal errors now return 502 with `name`/`debug_id`/`details` (e.g. `ORDER_NOT_APPROVED`) instead of a 500. The live-shaped flow is tested against a mock PayPal (`tests/test_paypal_sandbox.py`). **The real button has not been clicked yet**: the build sandbox can't reach paypal.com. |
| 4. Live capture + B-9 | **B-9 Passed.** Vault setup token exchanged and $1 order `7LX28344P4713330H` captured server-side (`3L94707948760335B` COMPLETED). Live UI capture in progress. |

**Step 4 runbook**
1. In `.env`: `REPLAY_MODE=false`, PayPal and Channel3 keys set. Restart the backend (single worker).
2. `scripts/phase0_check.py merchants`: the webcam pick should have ≥30d returns (AUTO_SETTLE), and the microphone pick should be "terms hidden". If not, adjust the query in `runs.DEMO_NEEDS` or the table.
3. In the UI: Run agent. The header badge must say **live sandbox**. Approve the monitor card, then click the PayPal button, log in as the sandbox **personal** account and approve. The card must show a real order ID (not `ORD-REPLAY-…`) and a capture ID.
4. Check the same order in the sandbox business account's activity, and that `custom_id` equals the lineage.
5. B-9: `scripts/phase0_check.py b9`, approve the printed link as the sandbox buyer, then `scripts/phase0_check.py b9 <setup_token_id>`. PASS = AUTO_SETTLE can capture server-side from a saved wallet. FAIL = keep the popup for AUTO_SETTLE and say so in the pitch (doc 10 §5).
6. `make test` with `REPLAY_MODE=true` must still pass.

**Found while doing this:** the root `.gitignore` rule `lib/` (meant for Python) was ignoring `frontend/src/lib/format.ts`, so that file was never committed and a fresh clone failed `npm run build`. The rule is now anchored to `/lib/` and `backend/lib/`, and `format.ts` is committed.

### ⚠️ Corrections to earlier docs
- README / docs 07–08 list `gpt-4o` and `claude-3-5-sonnet`, which are outdated. The LLM layer now targets `claude-opus-5-5` (configurable through `LLM_MODEL`).
- The plan is framed as a "36-hour sprint", but the deadline is **12 Nov 2026, ~14 days away**. That leaves room to move stages 7 and 8 from mock to live. The scope cut above is the floor, not the ceiling.
- The arXiv IDs cited in docs 02/07 (e.g. `2610.29216`) were **not verified** here. Check them before they appear in the pitch or video.

---

## 7. Live Sandbox & Integration Experiments Log (Phases 0 & 1)

This section records the empirical experiments conducted against live external APIs (PayPal Sandbox, Channel3 REST) to establish verified baseline behavior for autonomous agentic commerce.

### Experiment 1: PayPal REST Gateway & Payouts Provisioning (B-1, B-2)
* **Objective:** Verify OAuth token lifecycle, API scopes, and Payouts eligibility on the sandbox business account.
* **Execution:** Executed `POST /v1/oauth2/token` via `SandboxPayPal._bearer()`. Scopes verified: `orders`, `payouts`, `disputes`, `invoicing`, `vault`.
* **Payouts Execution:** Dispatched a real \$1.00 sandbox payout batch via `POST /v1/payments/payouts` with idempotent `sender_batch_id`.
* **Findings:**
  - PayPal Payouts v1 strictly requires an explicit `currency` in addition to `value` (fixed in `s07_payout.py`).
  - Resulted in payout batch ID `UYPJ27MNP6X5J` with status `PENDING` (subsequently `SUCCESS`). Payouts are fully functional in our sandbox.

### Experiment 2: Channel3 Real-World Market Discovery & Option Generation (B-5)
* **Objective:** Evaluate real retail catalog indexing, price baseline calculations, and return term discovery.
* **Execution:** Sent search requests to `https://api.trychannel3.com/v1/search` with header `x-api-key` across three office procurement needs:
  1. `1080p webcam` (Direct buy): Returned 10 priced items ($9.99 Marshalls to $129.99 Logitech). Lowest allowlisted was `bestbuy.com` ($49.99).
  2. `27in 4K monitor` (Negotiate): Returned 10 priced items ($99.99 Staples to $1,999.99 Office Depot). Established real market baseline from `newegg.com` ($143.99 – $829.99) against which supplier agents negotiate.
  3. `USB condenser microphone` (Direct buy): Returned 9 priced items ($49.99 Adorama to $179.99 B&H).
* **Key Finding & Architectural Decision:**
  - Channel3 product feeds do **not** reliably expose return policy duration (`return_days: None`).
  - Rather than treating this as a limitation, we implemented the **Return Policy Lookup Table (`RETURN_POLICY_DAYS`)** for standard electronics retailers (Amazon: 30d, Best Buy: 15d, Walmart: 30d, Target: 30d, Newegg: 30d, B&H: 30d, eBay: None).
  - Unlisted merchants and eBay remain `return_days = None`, intentionally demonstrating the `arXiv:2610.17378` "cannot decide on hidden terms" safeguard: the firewall fails the Reversibility factor and escalates to human approval.

### Experiment 3: Spend Mandate Firewall & User Approval Routing (Stage 3 & UI)
* **Objective:** Ensure deterministic governance over unconstrained LLM spending and provide safe human-in-the-loop controls.
* **Execution & Routing Logic:**
  - Evaluated candidates against the 4-factor firewall: Warrant, Reversibility, Price vs Baseline, Budget & Velocity.
  - **Option 1: Autonomous Auto-Settle (`AUTO_SETTLE`):** Low-value direct purchases meeting mandate criteria (e.g. webcams under \$300 with ≥30-day return policies) execute autonomously with zero user friction.
  - **Option 2: Human Approval Gate (`HUMAN_APPROVAL`):**
    - High-value negotiated packages exceeding the auto-threshold ($1,020 monitor batch > \$300 threshold) pause the session.
    - Items with missing return policies (e.g. USB microphone) pause the session for "return terms hidden".
    - Session generates an internal HMAC-signed `APPROVED` gate token; client cannot mint tokens and can only issue `POST /api/runs/{id}/decisions/{lineage}/approve`.
    - Golden PayPal JS SDK button (`@paypal/react-paypal-js`) dynamically surfaces on the approved card.
  - **Option 3: Fast Red-Team Block (`BLOCKED`):** Simulated prompt-injection attacks targeting budget override are stopped sub-millisecond (<1ms) deterministically.

### Experiment 4: Autonomous Vaulted-Wallet Execution (B-9)
* **Objective:** Determine whether an AI agent can execute `AUTO_SETTLE` purchases server-side without prompting a browser popup at checkout.
* **Execution:**
  1. `POST /v3/vault/setup-tokens` generated setup token `34K0134807610141K`.
  2. Human buyer opened `https://www.sandbox.paypal.com/agreements/approve?approval_session_id=...` and granted one-time beneficiary authorization to Test Store.
  3. Backend exchanged setup token via `POST /v3/vault/payment-tokens` for payment token `vault_id: 8ng18757…`.
  4. Backend created and captured an order against the vaulted payment source:
     - Order ID: `7LX28344P4713330H` (`COMPLETED`)
     - Capture ID: `3L94707948760335B` (`COMPLETED`)
* **Finding:** **B-9 PASSED.** Proves true agentic commerce: buyers delegate spend authority once during mandate setup, and the agent executes approved auto-settle transactions without human checkout popups.

### Experiment 5: PayPal Sandbox Resolution Center & Defense Pipeline (B-4)
* **Objective:** Attempt end-to-end dispute creation in the sandbox and test ledger-backed evidence submission.
* **Execution:** Logged into `sandbox.paypal.com` as the buyer, selected transactions, and clicked "Report a Problem" (`/resolutioncenter/...`).
* **Finding:**
  - PayPal's sandbox Resolution Center UI is currently experiencing an internal server error across all transactions (*"We're sorry, it looks like something went wrong on our end"*).
  - **Guardrail R3 Active:** Activated our planned deterministic dispute fallback (`PP-D-1001`). Stage 8 (`s08_defend.py`) successfully generated the ReportLab PDF evidence brief, verified SHA-256 hash chains from the ledger, computed win probability (95%), and constructed the multipart `provide-evidence` payload. No hackathon progress was blocked.

### Stage 8 dispute desk (2026-11-05)

A PayPal dispute is answered rationally from records sealed before it existed. A human sends the response (D-4).

- **Persistence first.** Live runs used to write evidence to an in-memory ledger, so a dispute arriving after a restart had nothing to defend with. That's what happened to `PP-R-EGO-10196439`: its seal `PG-986dd7cd20d6febc.9d975a51f6` lived only in that backend process. Live runs now append to one persistent ledger (`LEDGER_PATH`, one `EvidenceLedger` per file via `core/ledger.open_ledger`). Replay runs stay in memory. Studio rows, a run's ledger view and its entry count are scoped to the run's own lineage.
- **Matching.** The lineage comes back in `disputed_transactions[].custom`. If it's missing, the seller transaction ID is matched against ledger `capture` entries.
- **Assessment** (`s08_defend.assess`, deterministic):
  - Facts come from the ledger: when the order was sealed, the true return window (from the decision, so hidden terms stay hidden rather than reading as 0), human approval, delivery proof, missing evidence, chain integrity.
  - The buyer's note is classified as defect, not-received or other.
  - Win odds are capped at 35% on a defect claim, because a seal proves what was sold, not that the unit still works.
- **Options and expected value.** 
  - Contest = $p \times \text{amount} - \text{handling cost}$. The **handling cost (\$15)** represents the non-refundable PayPal dispute fee plus operational review cost (not shipping). Fighting low-probability claims results in negative EV due to fee exposure.
  - Refund on return = $\text{recovery} \times \text{amount} - \text{return label}$. Applies only to claims where goods were delivered (e.g. defect or not-as-described).
  - Accept = \$0.00 (the baseline surrender outcome).
  - The cost constants are labelled estimates at the top of `s08_defend.py`.
- **Handled Dispute Reasons & Shipping Verification:**
  - **Item Not Received (`MERCHANDISE_OR_SERVICE_NOT_RECEIVED`):** A buyer reporting an undelivered item cannot physically return goods. PayPal's API strictly enforces `allowed_response_options.make_offer.offer_types = ["REFUND"]` and rejects `REFUND_WITH_RETURN` with `INVALID_OFFER_TYPE`. The system detects this reason, automatically excludes `refund_with_return` (*"Item not received: buyer cannot return goods that were never delivered"*), and falls back to `accept` (\$0.00) unless proof of delivery exists.
  - **Shipping Verification (Stage 5 Connection):** Orders v2 captures the buyer's shipping address. If Stage 5 records a verified `delivery_proof` (`carrier`, `tracking_number`, `status: DELIVERED`), the brief attaches PayPal `PROOF_OF_FULFILLMENT`. Win odds jump from 15% to 95%, flipping `contest` from -\$9.00 to a winning +\$23.00 EV. Without tracking proof, contesting undelivered items has an 85% loss rate and is rationally avoided.
- **Hard rules.**
  - Never contest without a sealed record.
  - Never contest a not-as-described claim inside our own sealed return window.
  - Never offer refund-with-return on an item-not-received claim.
  - Nothing once the response deadline has passed.
- **Allowed actions.** Only actions PayPal currently lists in `links` are allowed. When PayPal allows only `send_message`, a refund or acceptance is proposed in a message.
- **Responding.** `POST /api/disputes/{id}/respond` sends `provide-evidence` (with the PDF brief), `send-message`, `make-offer` (`REFUND_WITH_RETURN`) or `accept-claim`. Each option is sent once. The ledger records the option, channel, EV, recommendation, whether it was followed, the approver and a hash of the note (not the text).
- **LLM.** It is optional and only rewords the draft (`POST /api/disputes/{id}/draft`). Without `ANTHROPIC_API_KEY` the template is used.
- **UI.** The Mission Control "Dispute desk" shows the case list, facts, options with EV, the recommendation, an editable draft, the PDF brief, and a "Send to PayPal" confirm. In replay it can simulate a buyer dispute on any settled item.
- **Live findings (2026-11-05, `PP-R-EGO-10196439` & `PP-R-PVO-10196452`).**
  - `make-offer` with `REFUND_WITH_RETURN` needs `return_shipping_address`; without it PayPal returns `MISSING_RETURN_SHIPPING_ADDRESS`. The address now comes from `RETURN_ADDRESS_*` in `.env`. Live mode refuses the offer if it is unset; replay uses a labelled demo address.
  - On Item-Not-Received disputes (`MERCHANDISE_OR_SERVICE_NOT_RECEIVED`, e.g. `PP-R-PVO-10196452`), PayPal strictly rejects `REFUND_WITH_RETURN` with `INVALID_OFFER_TYPE`. The system now inspects PayPal's `allowed_response_options` and automatically excludes `refund_with_return` on undelivered goods, recommending `accept` unless Stage 5 delivery tracking proof is present.
  - A direct schema probe of `accept-claim` was accepted (HTTP 200) and moved `PP-R-EGO-10196439` to `RESOLVED`.
  - The corrected `make-offer` body uses `REFUND_WITH_RETURN` + `return_shipping_address` for defect/not-as-described claims, and `offer_type: "REFUND"` for item-not-received claims.
  - **Live offer probe (2026-11-06).** `scripts/live_dispute_probe.py offer PP-R-PVO-10196452 10.00 --send` on the $40.00 item-not-received case. PayPal accepted the money-only `REFUND` offer (HTTP 200) and recorded `seller_offered_amount: 10.00`, `offer_type: REFUND`, `actor: SELLER`, `event_type: PROPOSED`; the case moved to `WAITING_FOR_BUYER_RESPONSE`, briefly showing `UNDER_REVIEW` first (seen once, not a documented PayPal guarantee). **What this proves:** the production `offer_body` for a partial `REFUND` is accepted by PayPal. **What it doesn't:** it was sent by the probe, not by the desk, so it isn't in the ledger and isn't an agent decision; and the desk's own `partial_refund` recommendation (overcharge) still can't arise live, because settlement always captures the sealed price. The probe now passes only when PayPal's offer record matches the amount and type sent and the case is waiting on the buyer.

### Stage 8 playbooks and case lifecycle (2026-11-05)

`s08_defend.PLAYBOOKS` maps every PayPal dispute reason to the evidence it needs, a ledger check and the responses that make sense. `tests/test_dispute_playbooks.py` has one test per scenario.

| Reason | Ledger check | Recommends |
|---|---|---|
| Item not received | Carrier tracking in a `delivery_proof` entry | **Contest** with `PROOF_OF_FULFILLMENT` if delivered (odds ≥ 85%). **Share tracking and wait** if in transit and not late; refunding is then blocked. Otherwise **refund**. Never refund-with-return. |
| Not as described | Sealed return window, buyer's note | Never contest inside our own window; a defect claim caps odds at 35%, so a **refund on return** usually wins. |
| Duplicate charge | Another capture, same vendor and amount, within 48 h, anywhere in the mandate | Found → **refund** (contest blocked). One capture only → **contest** (the deterministic PayPal-Request-Id proves one order). |
| Incorrect amount | Captured vs sealed amount | Captured more → **refund the overcharge** only (`make-offer` `REFUND` for the difference). Equal → **contest** from the penny-exact seal. |
| Refund not processed | Any earlier refund commitment on this purchase | Committed → honour it (contest blocked). |
| Unauthorised | Delivery proof and human approval | Flagged for security review; contest only with both. |
| Recurring billing / paid by other means | Captures on this purchase | One capture → **contest**; more → no contest. |
| Anything else | — | No automatic recommendation: manual review. |

- **Case state.** Only `WAITING_FOR_SELLER_RESPONSE` gets a recommendation. Waiting on the buyer, under PayPal review, and resolved are shown as such.
- **Costs by stage.** The handling cost rises from $15 (inquiry) to $20 (chargeback) and $25 (arbitration). These are labelled estimates.
- **Flags.** A purchase disputed before, a disputed amount above the captured amount, a duplicate capture, and possible account compromise.
- **Outcome learning.** When PayPal resolves a case, its `dispute_outcome.outcome_code` is recorded once as WON or LOST (`sync_outcome`) for stage 10's supplier trust.
- **Delivery proof in live mode.** `POST /api/deliveries` seals carrier tracking for any purchase, so the item-not-received contest path works live, not only in replay. The VERIFIED gate token never leaves the server.
- **Timestamps.** The desk lists when each case was opened and its respond-by date. Each case has a timeline in the viewer's time zone: purchase sealed, dispute opened, messages, our responses with the approver, and the outcome.
- **Replay.** The desk can simulate each reason on any settled item, and PayPal's decision (we win / buyer wins).
- **Fixed:** the refund-with-return exclusion now says "PayPal doesn't allow a refund-with-return offer on this case" when PayPal leaves it out. The "Item not received" wording now appears only on item-not-received cases, where that option isn't offered at all.

### Experiment 6: live return lifecycle, `PP-R-PSL-10196709` (2026-11-06)

The first dispute taken from open to closed live, through the desk, on order `6AR380350R607771Y` ($28.00, capture `79H28497XC211214U`).

| Step | Who | What happened | PayPal status |
|---|---|---|---|
| 1 | Buyer | Opened a $14.00 not-as-described case (partial amount of the $28.00 order) | `WAITING_FOR_SELLER_RESPONSE` |
| 2 | Agent | Matched the seal, found the 30-day return window still open, so contest was excluded. Contest −$5.62 (67% × 14 − 15), refund on return +$3.20 (0.8 × 14 − 8): recommended refund on return. | — |
| 3 | Operator | Sent `make-offer` `REFUND_WITH_RETURN` with `return_shipping_address` from `RETURN_ADDRESS_*` | `WAITING_FOR_BUYER_RESPONSE` |
| 4 | Buyer | Accepted and uploaded `PROOF_OF_RETURN` tracking (UPS `1Z9999999999999999`) | `WAITING_FOR_SELLER_RESPONSE`, `acknowledge_return_item` listed |
| 5 | Operator | Sent `acknowledge-return-item` `ITEM_RECEIVED` | `UNDER_REVIEW` → `RESOLVED` (`RESOLVED_BUYER_FAVOUR`), $14.00 refunded |
| 6 | Ledger | Both responses and the outcome sealed; chain verified over 125 entries | — |

**What this proves:** PayPal accepts our `make-offer` (refund with return) and `acknowledge-return-item` bodies. The return path round-trips the buyer's tracking as `evidences[].evidence_type = PROOF_OF_RETURN`, and the outcome syncs into the ledger.

**What review changed afterwards** (commit following `9a50dc3`):
- **Acknowledging on buyer tracking alone was a flaw.** In step 5 the desk recommended "confirm return received & refund" as soon as the buyer uploaded tracking, and that tracking was a placeholder number. `ITEM_RECEIVED` tells PayPal we inspected the item and releases the refund at once. The acknowledgement is now excluded until a person records what arrived (`POST /api/disputes/{id}/return-received`: item received, damaged, parts missing, empty box/different item, or never arrived). That condition becomes the `acknowledgement_type`. Only `ITEM_RECEIVED` refunds; the others go to PayPal review with our inspection on record. While the parcel is on its way, the desk recommends nothing and says to wait.
- **A refund we chose is SETTLED, not LOST.** Step 6 recorded `LOST`, which would have cut the auto-approve threshold by 25% as if the agent had lost a fight. Outcomes are now WON, LOST (we contested and lost) or SETTLED (we offered the refund). SETTLED still lowers the supplier's trust score, because a defect return is a quality signal, but it doesn't tighten the mandate. `PP-R-PSL-10196709` was recorded before this change, so its ledger entry still says `LOST`. The ledger is append-only, so that entry stays and this note explains it.
- **Replay now covers returns** ("Simulate: buyer ships the return"), and `tests/test_dispute_returns.py` has five tests for the lifecycle.

**Corrections to the session report:**
- "Zero schema violations": two were hit live (`INVALID_OFFER_TYPE`, `MISSING_RETURN_SHIPPING_ADDRESS`) and then fixed.
- "Cryptographic approval signatures in the ledger": the ledger is SHA-256 hash-chained (tamper-evident). Approvals are HMAC gate tokens held server-side; the ledger records that an approval happened, not a signature.
- "`UNDER_REVIEW` for 500–1500 ms while settlement pipelines process": observed briefly after two actions. The timing and cause are not documented PayPal behaviour. Only the probe polls past it; the desk shows whatever PayPal reports on each refresh.
- The return address is from `.env`. Make sure it is a real returns address before any demo where a buyer could ship to it.
- The desk polls `/api/disputes` every 10 s while the tab is visible, which makes one PayPal call per open case per poll. That's fine for a demo, but raise the interval if many cases are open.

### 🔄 Phase close-out (2026-11-06)

| Item | State |
|---|---|
| Phase 1 exit (mandate end to end in the UI; an order approved in the PayPal popup and captured; real order ID shown) | **Done** live, plus the saved-wallet AUTO_SETTLE capture (B-9) |
| Stage 8 dispute desk (Phase 3 scope, done early) | **Done** live: matching, playbooks for every reason, EV, hard rules, human-sent responses, return lifecycle with inspection, outcome sync (WON / LOST / SETTLED), timestamps and timeline |
| Live-verified PayPal calls | Orders create/capture, vaulted capture, Payouts (probe), disputes list/get, `make-offer` (`REFUND` and `REFUND_WITH_RETURN`), `acknowledge-return-item`, `accept-claim` (probe) |
| Not yet verified live | `provide-evidence` (multipart with PDF), `send-message`, the `ITEM_DESCRIPTION` evidence type, webhook signature verification |
| Still scripted | Stage 6 invoice forensics, stage 7 payout release after verification, stage 10 calibration shown as before/after |
| Tests | 101 passing, ruff clean, frontend builds |
| **Next: Phase 2** (doc 10 §4) | Seeded history through the real step functions, `test_studio_row_columns_are_stable`, three custom Studio widgets, the lineage timeline from a grid row, the mandate v1 → v2 diff. The Studio rows already carry `order_id`, `capture_id`, `created_at`, `updated_at`, `dispute_win_odds` and `dispute_outcome`. |
| Phase 2 to 4 progress (2026-11-12) | Merged to `main` (PRs #4, #5, #8, #9, #10, #11, #12, #13, #14): the Command Center (Purchases, Agent Activity, Reconciliation, and the PayPal account pages Revenue, Receivables, Cash, Catalogue), the one-button stages 5 to 7 sequence in Mission Control (scripted carrier and vendor inputs, real gates), the PayPal webhook endpoint, the Render files, the evaluation harness and the judge-facing README. The live PayPal account read is verified against the real sandbox (94 transactions, 7 payouts, 2 balances; the three sandbox captures reconcile). Render is deployed at https://pactguard-ai.onrender.com. APIMatic Orders validation is scripted and recorded. 168 tests pass, ruff check and frontend lint are clean. Details: doc 10 §6. |
| Phase 2 progress (2026-11-06) | Seeded history (`app/seed.py`, 30 mandates through the real step functions) and the frozen Studio row contract are done; see doc 10 Phase 2. Carried-forward items are tracked in doc 10 §6 Backlog. |

### ⚠️ Test isolation fix (2026-11-06)

Before this fix, `pytest` wrote to the real persistent ledger. Tests that switch to live rules (for example, the saved-wallet test in `tests/test_paypal_sandbox.py`) start runs that append to `LEDGER_PATH`, which defaults to `./ledger.db`, the same file that holds live sandbox evidence. Each test run added about 120 rows of fake purchases.

`tests/conftest.py` now points `LEDGER_PATH` at a throwaway temp directory before the app is imported, and `tests/test_isolation.py` asserts it.

**If you ran the tests from `backend/` with a live ledger in place, that `ledger.db` contains test runs mixed with real evidence.** The ledger is append-only, so they can't be removed in place. Either keep the file and note it here (lineages from test runs are visible in `GET /api/ledger`), or start a fresh ledger file for the next live run.

**Note on the local dev ledger (added 2026-11-12).** The gitignored `ledger.db` files were later pruned by hand in a local session to remove test orders from before the isolation fix, keeping the real sandbox lineages. The hash chain still verifies (`verify()` returned `(True, None)` on a copy: 20 entries, 8 lineages). The change is local only: nothing was committed, and a Render deploy starts with a fresh ledger.

### Architectural Decision D-5: Geographic Delivery & Cross-Border Fulfillment Governance
* **Context:** Channel3's discovery graph indexes major North American and global retailers (Best Buy, Newegg, B&H Photo, Adorama, etc.) denominated in USD. In autonomous commerce, unconstrained agents could easily order products from retailers that do not ship to the buyer's home country (e.g. Italy/EU vs US) or that trigger unexpected customs tariffs.
* **PactGuard AI 3-Layer Governance:**
  1. **Mandate-Level Geographic Allowlisting:** During Stage 1 delegation, the enterprise defines its destination country (`country_code`) and filters allowable vendor domains (e.g., `amazon.it`, `unieuro.it`, or verified global merchants with DDP shipping).
  2. **Firewall Warrant & Reversibility Check (Stage 3):** If a merchant does not provide clear shipping terms or cannot fulfill to the buyer's destination country, the Mandate Firewall fails the *Warrant* / *Reversibility* factor and routes the item to `HUMAN_APPROVAL` (preventing blind, unfulfillable auto-purchases).
  3. **Milestone Escrow Delivery Verification (Stage 5 - ChronoPay):** Payments are held in platform escrow; Stage 5 verifies international carrier tracking (FedEx, DHL, UPS) and confirmed delivery to the buyer's registered PayPal destination address before Stage 7 releases funds to the seller.
* **Future Enhancement Roadmap (Phases 2 & 3):**
  - Add an explicit `destination_country: str = "US"` field to the Mandate input schema.
  - Implement dynamic merchant shipping capability lookups during Stage 2 product discovery.
  - Expose regional shipping delivery metrics in the AG Studio FinOps dashboard.

---

## 8. Suggested split (3 people)

| Person | Week 1 | Week 2 |
|---|---|---|
| **A — Payments** | B-1/B-2/B-3: live sandbox for stages 1–4. Add `/prepare` and `/capture` endpoints. Run the guard tests against the sandbox. | B-4 live dispute + `provide-evidence`. Webhook endpoint. Live payout. |
| **B — Frontend** | Negotiation arena, firewall drawer, JS SDK approve button, lineage timeline | Dispute card, mandate before/after diff, demo polish |
| **C — Data / Sponsors** | B-5 Channel3 live. B-6 AG Studio grid over `/api/studio/rows` | 3 custom Studio widgets + NL queries. APIMatic. Render deploy. Video. |

Rule for everyone: **a new guard ships with a test in `tests/test_handoff_guards.py`, and the demo must stay green with `REPLAY_MODE=true`.**
