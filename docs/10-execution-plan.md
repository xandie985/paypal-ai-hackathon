# Section 10: Execution Plan — Phased Delivery

This document turns the research (docs 01–08) and the implementation framework (doc 09) into a **phased build plan**. It covers three things:

1. **Current state.** What is broken today for PayPal developers and merchants, using the evidence gathered in [03](03-user-pain-points-and-signals.md), [02](02-literature-and-technical-landscape.md) and [04](04-competitor-and-prior-art.md). It also covers where our own code stands.
2. **How we solve it.** Each problem is mapped to a mechanism, a module and a phase. The problems are grouped into clusters, and each cluster gets effort in proportion to its weight.
3. **Phase technicalities.** For each phase: the endpoints, files, sandbox steps, tests, risks and exit criteria.

The UI and dashboard work for every phase is in [doc 11](11-dashboard-ui-plan.md). It covers the design system, the screens, AG Studio details and a UI task tracker that runs alongside these phases.

> **As of:** Saturday 2026-10-31. **Deadline:** Thursday 2026-11-12, 12:00 PM PST. That leaves **12 days**, and we plan to submit on **Nov 11**.

> **Progress (2026-11-06):** Phase 0 and Phase 1 are closed. Stage 8 from Phase 3 (the dispute desk) is done early and verified live, including a full return-refund lifecycle. **Phase 2 starts now.** Status and open items: [doc 09 Phase close-out](09-implementation-framework.md#-phase-close-out-2026-11-06).

> **Progress (2026-11-12):** Phases 2, 3 and 4 are built and merged to `main` (PRs #4, #5). The Command Center grew from one flat table into a six-page AG Studio report: **Agent** (`Purchases`, `Agent Activity`) and **PayPal account** (`Revenue`, `Receivables`, `Cash`, `Catalogue`), with PayPal and lineage detail drawers joined on `capture_id`. See the Phase 2 addendum below. 155 tests pass. Still open: the live PayPal read (only mock-tested), the Render deploy, APIMatic, and the backlog in §6.

---

## 1. Current state

### 1.1 What is broken today

The 12 pain points in doc 03 fall into four groups. The links are the sources recorded in doc 03. Phase 0 re-checks each one before it appears in the pitch (see §4, Phase 0).

#### A. Agents can spend money, but nothing governs the spend
| # | Pain point | Evidence | What developers do today |
|---|---|---|---|
| 1 | `paypal/agent-toolkit` has no spend cap and no human gate before order capture. The official LangChain and CrewAI examples enable capture. | [Issue #95](https://github.com/paypal/agent-toolkit/issues/95), [Issue #105](https://github.com/paypal/agent-toolkit/issues/105) | Remove `pay_order`, which leaves a read-only bot, or hand-write wrapper scripts |
| 2 | None of the 46 MCP tools declares read/write/destructive hints. `PayPal-Request-Id` is set per client, not per call, so a retry can double-charge. Before a fix, `create_invoice` sent live invoices instead of drafts. | [Issue #114](https://github.com/paypal/agent-toolkit/issues/114), [Issue #98](https://github.com/paypal/agent-toolkit/issues/98), [PR #94](https://github.com/paypal/agent-toolkit/pull/94) | Fork the SDK and patch `client.ts` |
| 8 | `create_order` serialised tax so that PayPal rejected it with `AMOUNT_MISMATCH`. `get_order_details` reported "successfully captured" for `PAYER_ACTION_REQUIRED` and `VOIDED` orders. | [PR #110](https://github.com/paypal/agent-toolkit/pull/110), [PR #115](https://github.com/paypal/agent-toolkit/pull/115) | Hand-written arithmetic validators, and reading raw status codes |
| 12 | OpenAPI spec inconsistencies: `list_product` vs `list_products`, string vs number for `unit_amount`, `allOf` bugs. These break codegen and make LLMs hallucinate parameters. | [specs PR #50](https://github.com/paypal/paypal-rest-api-specifications/pull/50), [Issue #40](https://github.com/paypal/agent-toolkit/issues/40) | Reading SDK source to find the real parameter shapes |

#### B. Agentic shopping breaks between "found it" and "paid for it"
| # | Pain point | Evidence | What people do today |
|---|---|---|---|
| — | 18.9% of merchant sites block declared agents. Over 90% don't expose machine-decidable all-in totals or return terms. | `arXiv:2610.17378` (doc 02 §3) | 15 browser tabs and a spreadsheet |
| — | Unconstrained LLM negotiators get stuck in polite loops, emit malformed output and double-commit across parallel sellers. | `arXiv:2610.11542`, `arXiv:2610.06017` (doc 02 §4–5) | Email back-and-forth, then a manual PayPal invoice |

#### C. After the purchase: payouts, invoices, lineage
| # | Pain point | Evidence | What people do today |
|---|---|---|---|
| 5 | Agent-initiated transactions lose their facilitator or agent attribution by the time a dispute arrives. | [Issue #113](https://github.com/paypal/agent-toolkit/issues/113) | Cross-referencing IDs across gateway logs by hand |
| 6 | Freelancers chase unpaid milestone invoices. Schedules and payments live in separate tools. | [HN #17146946](https://news.ycombinator.com/item?id=17146946), [r/freelance](https://www.reddit.com/r/freelance/comments/ivipfs/i_asked_a_client_about_some_unpaid_invoices_what/) | Reminder emails and manual date shifting |
| 7 | The toolkit can take money in but can't pay anyone out. Gross-vs-net fee and FX reconciliation is painful. | [PR #107](https://github.com/paypal/agent-toolkit/pull/107), [r/smallbusiness](https://www.reddit.com/r/smallbusiness/comments/2xx3v0/how_do_you_account_for_paypal_transaction_fees/), [SO #68591697](https://stackoverflow.com/questions/68591697/paypal-payout-fails-to-some-accounts) | CSV exports, spreadsheet macros, batch upload |
| 9 | Spoofed vendor invoices are sent through PayPal's real invoicing servers, so they get past spam filters. | [HN #40595650](https://news.ycombinator.com/item?id=40595650), [HN #26998909](https://news.ycombinator.com/item?id=26998909) | Checking every invoice against vendor records by eye |
| 11 | Webhook verification fails (`VERIFICATION_FAILURE`) because frameworks alter the raw body. Handlers that aren't idempotent cause retry storms. | [SO #75306849](https://stackoverflow.com/questions/75306849/verifying-paypal-webhook-keeps-failing-verification-status-failure), [SO #78248486](https://stackoverflow.com/questions/78248486/how-to-fix-webhook-signature-verification-failed-in-paypal-node-js-webhook), [WooCommerce #4559](https://github.com/woocommerce/woocommerce-paypal-payments/issues/4559) | ngrok, trial-and-error with headers, manual replay |

#### D. Disputes: merchants can only surrender
| # | Pain point | Evidence | What merchants do today |
|---|---|---|---|
| 3 | The toolkit has `list_disputes`, `get_dispute` and `accept_dispute_claim`, which concedes the dispute. It has nothing to submit evidence. Developers calling `provide-evidence` by hand hit `INVALID_EVIDENCE_FILE`. | [PR #109](https://github.com/paypal/agent-toolkit/pull/109), [PR #118](https://github.com/paypal/agent-toolkit/pull/118), [SO #78902643](https://stackoverflow.com/questions/78902643/paypal-disputes-api-returns-invalid-evidence-file-when-posting-file) | The Resolution Center UI by hand, or Chargeflow at a 25% success fee |
| 4 | Digital-goods and SaaS merchants lose "not as described" disputes and get hit by waves of bot disputes. Winning needs timestamped logs, terms hashes and delivery proof. | [HN #44176510](https://news.ycombinator.com/item?id=44176510), [HN #45993166](https://news.ycombinator.com/item?id=45993166), [r/paypal](https://www.reddit.com/r/paypal/comments/dxnurx/how_to_prevent_chargebacks_on_digital_goods/) | Screenshotting logs and stitching PDFs for every dispute |

**Not addressed:** #10, SaaS subscription sprawl ([r/sysadmin](https://www.reddit.com/r/sysadmin/comments/1q5qy6x/how_are_you_handling_saas_sprawl_without_a_20k/)). It's a real problem but sits outside our loop. Adding it would spread the demo thin.

### 1.2 What the research tells us to build
Every design choice below traces to a paper in doc 02. Doc 09 §7 notes that these arXiv IDs have not been independently verified yet. Phase 0 does that.

| Finding | Paper (doc 02) | What it becomes in our code |
|---|---|---|
| LLMs **overreach** past the "auto-purchase line". Four factors predict where a human should be asked: warrant, reversibility, price norm, urgency. | `2610.29216` | 4-factor Mandate Firewall, [`s03_govern.py`](../backend/app/stages/s03_govern.py) |
| Bind approvals to a **canonical transaction digest**, not to a session | `2610.22899` | `decision_digest` and HMAC gate tokens, [`core/gates.py`](../backend/app/core/gates.py) |
| Agents can't **decide** (hidden terms) or **prove** (no record) | `2610.17378` | Decide-and-Prove seal at settlement, [`s04_settle.py`](../backend/app/stages/s04_settle.py) |
| Negotiators loop, emit bad schemas and deadlock. A constitutional gate fixes this. | `2610.11542` | `schema_gate` and `MAX_TURNS = 3`, [`s02_negotiate.py`](../backend/app/stages/s02_negotiate.py) |
| Parallel sellers replace price concession, but risk **double commitment** | `2610.06017` | `ReservationBook` reserve-then-commit |
| Behaviour-aware guards (APPROVE / REVIEW / REJECT) catch injected delegation | `2610.27483` | `scan_injection` plus the routes `AUTO_SETTLE` / `HUMAN_APPROVAL` / `BLOCKED` |
| Embeddings collapse on look-alike invoices. Lexical plus structural matching beats them. | `2606.25343` | BM25 and trigram forensics, [`s06_reconcile.py`](../backend/app/stages/s06_reconcile.py) |

### 1.3 Where our code stands

| Area | State | Gap that matters for the plan |
|---|---|---|
| Core primitives: ledger, lineage, gates, money | Built, with tests | None |
| Stages 1–10 | Built. The full arc runs in replay mode. | Stages 5, 6, 7 and 10 are scripted rather than live |
| Tests | 155 passing (2026-11-12) | None |
| API, [`api.py`](../backend/app/api.py) | `POST /api/demo/run`, `GET /api/ledger`, `/ledger/verify`, `/studio/rows` | **`/demo/run` is one synchronous call.** A UI can't pause for human approval, and a real PayPal order can't wait for buyer approval. This is the first task in Phase 1. |
| Orchestrator, [`orchestrator.py`](../backend/app/orchestrator.py) | `run_demo` runs the whole arc and calls `asyncio.run(negotiate(...))` | `asyncio.run` can't be called from inside an async endpoint. Negotiation has to be awaited directly. |
| PayPal client, [`integrations/paypal.py`](../backend/app/integrations/paypal.py) | `SandboxPayPal` covers Orders v2, Invoicing v2, Payouts v1, `provide-evidence` and webhook verify, with OAuth caching | Run live in Phases 0 and 1. Webhook verification now takes the raw body (Phase 3, pain point #11). |
| Channel3, [`integrations/channel3.py`](../backend/app/integrations/channel3.py) | Replay and live both work (`/v1/search`, `x-api-key`), verified in Phase 0 | None |
| LLM, [`integrations/llm.py`](../backend/app/integrations/llm.py) | Optional Claude layer with structured output and fallback | Not used by any stage yet. That's intended: it drafts text only. |
| Frontend | Mission Control, the dispute desk, the webhook inspector and the AG Studio Command Center (Phases 1 to 3) | UI polish sweep in Phase 4 |
| Deploy | `Dockerfile` and `render.yaml`; the API serves the built frontend; CORS comes from settings; verified locally as one process (2026-11-06) | Create the Render service from the Blueprint and fill in the secrets. Docker itself has not been run on this machine. |

---

## 2. How we solve them

### 2.1 Clusters and emphasis

The five ideas from doc 07 form one loop. They don't carry equal weight with the judges, so they don't get equal effort.

| Cluster | Stages | Absorbs | Pain points | Prize leverage | Effort | Depth |
|---|---|---|---|---|---|---|
| **A. Agentic commerce core** | 1 Delegate, 2 Discover / Negotiate, 3 Govern, 4 Settle | PactGuard | 1, 2, 8, B-group | Grand Prize, Agentic Commerce, PayPal + AI, Channel3 | **~40%** | Fully live on the sandbox |
| **B. Observe & Learn** | 9, 10 | PayPulse / AG Studio | 5 (lineage view) | AG Grid ($5k) | **~20%** | Live UI over real run data |
| **C. Defend** | 8 | AegisPay | 3, 4, 5 | Strong PayPal-judge moment, supports Grand Prize | **~15%** | One real sandbox dispute; the rest replay |
| **D. Post-purchase ops** | 5 Verify, 6 Reconcile, 7 Pay out | ChronoPay, HaystackAP | 6, 7, 9, 11 | Closes the loop. Low direct prize value. | **~10%** | Scripted. One live payout and a real webhook endpoint if time allows. |
| **Ship** | — | Render, APIMatic | 12 | Render, APIMatic, plus the submission itself | **~15%** | Deploy, evaluation numbers, video |

Clusters A and B are the product. C is a different area: there we act as the *seller*, while in A we're the *buyer*. It earns its place because it ends on the ledger built in A. D is glue: it has to appear in the demo, but it doesn't need to be live.

### 2.2 Pain point → solution map

| # | Our mechanism | Code | Live in | Demo moment |
|---|---|---|---|---|
| 1 | 4-factor firewall in front of **every** money movement (orders and payouts). Hard failures block, soft failures go to a human. | `s03_govern.evaluate` | Phase 1 | Three route cards: auto, approval, blocked |
| 1 | "Simulate attack": an injected $900 payout is blocked in under 1 ms | `scan_injection` and the warrant check | Phase 1 | Attack button, then BLOCKED with reasons |
| 2 | `PayPal-Request-Id = f(lineage, stage, operation, subject)`. A retry derives the same ID, so PayPal returns the original order. | `core/lineage.request_id` | Phase 1 | Retry button, same order ID |
| 2 | Draft-first invoicing: create, confirm `DRAFT` and the expected total, then send | `s04_settle.issue_invoice` | Phase 1 (approval path) | Pre-flight row in the settle drawer |
| 8 | Penny-exact purchase-unit builder, re-asserted before sending. Only `captures[0].status == COMPLETED` counts as captured. | `core/money.build_purchase_unit`, `s04_settle.capture` | Phase 1 | Pre-flight check row |
| B | Channel3 retail baseline feeds the firewall's price factor. Hidden return terms route to a human. | `s02_discover`, `LiveChannel3` | Phase 1 | Baseline price on each card, "return terms hidden" reason |
| B | 3-turn protocol, schema gate, reserve-then-commit | `s02_negotiate` | Phase 1 | Arena: malformed seller dropped, runner-up cancelled |
| 5 | One lineage ID in `custom_id`, `reference_id`, invoice `reference`, `sender_batch_id`, and on every ledger row | `core/lineage` | Phase 2 (UI) | Click a grid row to see its full lineage timeline |
| 3, 4 | Evidence built from records sealed **before** the dispute existed: seal, delivery proof and hash chain. Rendered to PDF and sent with `provide-evidence`. | `s08_defend` | Phase 3 | Dispute card: win odds, terms hash, "chain verified" |
| 7 | Payout requires both the `VERIFIED` and `RECONCILED` tokens. Gross-to-net split shown. Lineage-derived `sender_batch_id`. | `s07_payout.release_payout` | Phase 3 | Payout blocked, then released |
| 9 | Duplicate, payee-mismatch and amount-mismatch flags. No `RECONCILED` token is minted when flagged. | `s06_reconcile.InvoiceForensics` | Scripted | "NW 1001" resubmission flagged |
| 11 | Raw-body verification, dedupe by event ID, stored and replayable | `s07_payout.WebhookInbox` | Phase 3 | Duplicate webhook ignored |
| 6 | Tranche reschedule on a late delivery. Overdue-invoice nudges, once per day. | `s05_verify.reschedule`, `s07_payout.nudge_overdue` | Scripted | Timeline step only |
| 12 | APIMatic Context Plugin used while writing every live PayPal call. We document which payloads it validated. | — | Phase 4 | README section |
| — | Outcomes update supplier trust, which produces mandate v2 (with `parent_digest`) | `s10_learn.calibrate` | Phase 2 (UI) | Mandate before/after diff |

### 2.3 Rules that hold in every phase
1. **Money decisions are deterministic.** The LLM only drafts text: seller messages, dispute narratives, Studio answers. Its output goes through the same schema gate as any seller.
2. **Replay stays green.** `REPLAY_MODE=true` must run the full arc at the end of every phase, so there is always a recordable demo.
3. **Every new guard ships with a test** in `backend/tests/test_handoff_guards.py`.
4. **When something live breaks, that stage falls back to replay.** It never blocks the phase.
5. **Be honest about what's simulated.** Seller agents, carrier tracking and fee rates are simulated, and the UI and README say so.

---

## 3. Timeline

```text
            Sat31 Sun1 | Mon2 Tue3 Wed4 Thu5 | Fri6 Sat7 | Sun8 Mon9 | Tue10 | Wed11 | Thu12
Phase 0     ██████████ |                     |           |           |       |       |
Phase 1                | ███████████████████ |           |           |       |       |
Phase 2                |      ░░░░░░░░░█████ | █████████ |           |       |       |   ░ = start early on replay data
Phase 3                |                     |      ████ | █████████ |       |       |
Phase 4                |                     |           |      ████ | ███   |       |   feature freeze Tue 10 evening
Phase 5                |                     |           |           |   ███ | █████ |   submit Wed 11; Thu 12 is buffer only
```

| Phase | Dates | Cluster | Exit criterion (something you can demo) |
|---|---|---|---|
| 0. Unblock | Oct 31 – Nov 1 | — | Tests green locally. Sandbox credentials work. Dispute opened. Decisions recorded. |
| 1. Core loop live | Nov 2 – 5 | A | A real sandbox order created and captured from the UI, including the approval pause |
| 2. Observe & Learn | Nov 5 – 7 | B | An AG Studio prompt builds a widget from run data. Clicking a lineage opens its timeline. Mandate diff visible. |
| 3. Defend + ops | Nov 7 – 9 | C, D | `provide-evidence` accepted on the real sandbox dispute. Webhook endpoint verifying real events. |
| 4. Deploy & evidence | Nov 9 – 10 | Ship | Public Render URL runs the arc. Evaluation table in the README. |
| 5. Video & submit | Nov 10 – 11 | Ship | Devpost submission complete |

---

## 4. Phase technicalities

### Phase 0: Unblock (Sat Oct 31 – Sun Nov 1)

**Goal:** remove anything with lead time before any feature work starts.

**Environment**
```bash
make setup
```
```bash
make test
```
Expect 29 passing. If the number differs, fix it before Phase 1. Every later phase depends on these guards.

**Accounts and blockers.** These are doc 09's B-1 to B-8, plus B-9.
| ID | Action | How to verify it worked | Status |
|---|---|---|---|
| B-1 | Create a sandbox REST app. Put `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` in `.env`. Create sandbox **business** (us) and **personal** (buyer) accounts. | `POST /v1/oauth2/token` returns a token | **Done (PASS)** |
| B-2 | Check that Payouts is enabled on the sandbox business account | A $1 `POST /v1/payments/payouts` returns 201, not 403 | **Done (PASS, batch UYPJ27MNP6X5J)** |
| B-4 | Open a sandbox dispute. Buy something as sandbox buyer, then open a dispute in the sandbox Resolution Center. | `GET /v1/customer/disputes` lists it. Note when it reaches `WAITING_FOR_SELLER_RESPONSE`. | **Blocked on PayPal UI bug; Fallback R3 active (`PP-D-1001`)** |
| B-5 | Redeem `PAYPAL-HACKATHON-2026`. Read the Channel3 docs: path, auth header, response fields, whether return policy is exposed. | One real search returns products | **Done (PASS, `/v1/search` + return table)** |
| B-6 | **Done 2026-11-01.** AG Studio Pro with AI trial licence in `frontend/.env.local` (`VITE_AG_STUDIO_LICENSE`). Packages `ag-studio` and `ag-studio-react`, both 3.0.0. | `#/studio` renders run rows with the watermark hidden and no licence warning | **Done (PASS, closed 2026-11-01)** |
| B-7 | Render and APIMatic accounts | Logged in. Context Plugin installed in the editor. | Open |
| B-8 | `ANTHROPIC_API_KEY` (optional) | `make_llm` returns a client | Optional (skipped in preflight) |
| **B-9 (new)** | **Can AUTO_SETTLE capture without a buyer popup?** A server-created order needs buyer approval before capture. An "auto" purchase is only truly autonomous if the buyer has saved a PayPal wallet that we can charge later (vaulting). Check whether the sandbox app supports saving a PayPal wallet. | A test order against a saved wallet captures without a popup. If it doesn't, use the fallback in §5. | **Done (PASS, vault id `8ng18757…`, order `7LX28344P4713330H` captured)** |

**Decisions to record in doc 09 §7.** Each comes with a recommendation.
| ID | Question | Recommendation |
|---|---|---|
| D-1 | Who is the merchant in stage 8? | The business buys through PactGuard and resells or bills its own customers. A customer disputes, the business defends from the sealed record, and the loss counts against the supplier's trust score. |
| D-2 | How do funds flow in stage 7? | Escrow-style: the platform collects first and releases after verification. The pitch says so explicitly, and notes that production would use PayPal multiparty. |
| D-3 | What is the default mandate mode? | `auto` with a $300 threshold. `review_first` is shown as a toggle. |
| D-4 | Should dispute evidence auto-submit? This is doc 03's open assumption. | Default to "draft, then 1-click submit". Auto-submit is a mandate toggle. |
| D-5 | How is geographic delivery and cross-border fulfillment governed? | 3-layer protection: mandate vendor allowlisting by country/jurisdiction (e.g. EU vs US), firewall routing to human review on unverified or hidden shipping terms, and carrier tracking verification in Stage 5 before escrow payout disbursement. |

**Source check.** Open every arXiv ID in doc 02 and every GitHub, HN, Reddit and SO link in doc 03. Remove or correct anything that doesn't resolve. Only verified sources go into the video.

**Exit:** tests green, `.env` filled, dispute open, D-1 to D-4 recorded, source list checked.

---

### Phase 1: Core loop, live and visible (Mon Nov 2 – Thu Nov 5). Cluster A, ~40%.

**Goal:** a judge watches a mandate turn into a negotiated, governed, real PayPal sandbox order, with the human-approval pause in the middle.

**Pain points addressed:** 1, 2, 8, and the B group.

#### 1a. Run-session API (backend, first task)
`run_demo` can't pause, so the loop is split into step functions held in a run object.

- **New module `backend/app/runs.py`.** A `Run` dataclass holds the mandate, needs, offers, decisions, server-side gate tokens, and an `asyncio.Queue` of events. Runs live in a `RUNS: dict[str, Run]` registry in the process.
- **Step functions** wrap the existing stage calls unchanged: `delegate`, `discover`, `negotiate` (awaited, with no `asyncio.run`), `govern`, `approve`, `settle_prepare`, `settle_capture`.
- **`run_demo` is rebuilt on top of the steps**, auto-approving, so `test_full_loop_demo_arc` keeps guarding the whole arc. One code path serves both replay and live.
- **Gate tokens never reach the browser.** `s03_govern.approve` returns the `APPROVED` token into the run state, and the UI only sends "approve". A token in the browser could be replayed.
- **Events keep the current shape** (`{"stage", "event", ...}`, as `Runtime.log` produces), so the timeline renders the same in replay and live.
- The app must run with a **single uvicorn worker**, because run state is in process.

| Method & path | Purpose | Notes |
|---|---|---|
| `POST /api/runs` | Body: mandate and needs. Returns `run_id` and the mandate lineage. | Runs Delegate → Discover → Negotiate → Govern, then pauses |
| `GET /api/runs/{id}/events` | Server-sent events stream | `StreamingResponse`, `text/event-stream`; no extra dependency |
| `GET /api/runs/{id}` | Snapshot: decisions, offers, status | Lets the UI recover after a refresh |
| `POST /api/runs/{id}/decisions/{lineage}/approve` | Human approval | Only for `HUMAN_APPROVAL`. A `BLOCKED` decision returns 409. |
| `POST /api/runs/{id}/decisions/{lineage}/reject` | Human rejection | Feeds stage 10's rejection count |
| `POST /api/runs/{id}/orders/{lineage}/prepare` | JS SDK `createOrder`. Returns the PayPal order ID. | Calls `s04_settle.prepare_order`. Writes the seal. |
| `POST /api/runs/{id}/orders/{lineage}/capture` | JS SDK `onApprove` | Calls `s04_settle.capture`. Refuses if no seal exists. |
| `POST /api/runs/{id}/orders/{lineage}/retry` | Demo: re-sends create with the same request ID | Must return the **same** order ID |
| `POST /api/runs/{id}/attack` | Sends the injected $900 payout proposal through `evaluate` | Always `BLOCKED` |

`GuardViolation` maps to HTTP 409 with `e.to_dict()`, as `/demo/run` does today, so the UI can show the guard's name.

#### 1b. Live PayPal Orders (B-3, B-9)
- **Sandbox order states differ from replay.** Replay creates orders as `APPROVED`. The sandbox returns `CREATED`, and capture fails until the buyer approves. Flow: the UI calls `/prepare` and gets an order ID, the PayPal JS SDK button opens the buyer popup, `onApprove` calls `/capture`.
- **AUTO_SETTLE path:**
  - If B-9 passes, Delegate includes a one-time "authorise the agent's wallet" step in which the buyer saves a PayPal wallet. AUTO_SETTLE orders are then created against the saved wallet and captured server-side with no popup, so the agent really does pay.
  - If B-9 fails, AUTO_SETTLE skips *our* approval card but still opens the PayPal popup, and the pitch says so.
- `custom_id` and `reference_id` already carry the lineage (`core/money.build_purchase_unit`). We check that they come back on the captured order.
- The demo uses `tax_rate=0`. The penny-exact tax path stays covered by `test_tax_rounding_is_penny_exact_and_mismatch_is_caught`.

#### 1c. Live Channel3 (B-5)
- Only `LiveChannel3.search` and `_to_candidate` change. The rest of the code sees `ProductCandidate`.
- **Consequence 1: return terms.** If Channel3 doesn't expose return windows, `return_days=None` makes the reversibility factor fail. Every live item would then route to `HUMAN_APPROVAL`. Our approach:
  - For direct buys, keep a small, labelled return-policy table for the merchants in the demo query.
  - Leave one item routing to a human on "return terms hidden". This is the `arXiv:2610.17378` "can't decide" point, made visible.
- **Consequence 2: allowlist.** Real merchant names won't match `DEMO_MANDATE.vendor_allowlist`. Fix the demo query in Phase 0, then set the allowlist from the real merchants it returns.
- **The negotiating sellers are simulated** supplier agents (`SellerAgent`). Channel3 supplies the real retail baseline they're measured against. We say this on screen.

#### 1d. Frontend
> UI design and the remaining Phase 1 UI tasks (UI-0 foundation, UI-1 Mission Control) are in [doc 11 §11](11-dashboard-ui-plan.md#11-phase-by-phase-ui-plan-alongside-doc-10).

Stack: React 19, Vite, Tailwind 4 (already installed), and the PayPal JS SDK. We use v6 if the sandbox app supports it, otherwise `@paypal/react-paypal-js`.

| Component (`frontend/src/…`) | Shows | Backed by |
|---|---|---|
| `api/client.ts` | `fetch` wrappers and `EventSource` | All of the above |
| `features/mandate/MandateForm.tsx` | Budget, auto threshold, per-transaction cap, allowlist, categories, min return days, mode | `POST /api/runs` |
| `features/negotiation/NegotiationArena.tsx` | One column per seller and one row per turn. "Dropped by schema gate" badge with reason. Commitment hash. Reservation status (COMMITTED / CANCELLED). | `negotiated` event |
| `features/firewall/FirewallDrawer.tsx`, `RouteCard.tsx` | Three cards. Each shows the four factors as pass/fail with detail, reasons and latency. Approve and Reject buttons on the approval card. | `firewall` events, approve/reject |
| `features/settle/PayPalApprove.tsx` | JS SDK button, pre-flight row (breakdown consistent, request ID), resulting order and capture IDs | prepare and capture |
| `features/attack/AttackButton.tsx`, `RetryButton.tsx` | Injection blocked. Same order ID on retry. | attack and retry |
| `features/timeline/Timeline.tsx` | Event stream by stage | SSE |
| Header badge | Replay vs live, from `/api/health` | `GET /api/health` |

#### 1e. Tests to add
- `test_run_pauses_at_human_approval_and_resumes_on_approve`
- `test_blocked_decision_cannot_be_approved_via_api` (409)
- `test_retry_endpoint_returns_same_order_id`
- `test_approval_token_never_in_api_responses`
- `test_live_channel3_mapping` (a recorded JSON fixture run through `_to_candidate`)
- An SSE ordering test: stage events arrive in loop order.

**Risks**
| Risk | Fallback |
|---|---|
| The approval-pause refactor runs over | Hard stop on Thu Nov 5. Phase 2 has been building against replay since Nov 3, so it isn't blocked. |
| Sandbox is slow or down during recording | Header toggle back to replay. One live order ID is captured as proof. |
| B-9 fails | Use the popup path, and say so in the pitch |

**Exit:** in the UI, a mandate runs end to end. One order is approved through the PayPal popup and captured in the sandbox, and its real order ID is shown. Replay still passes `make test`.

> ✅ **Met (2026-11-05/06).** Also done: saved-wallet capture for AUTO_SETTLE (B-9 passed).

---

### Phase 2: Observe & Learn (Thu Nov 5 – Sat Nov 7). Cluster B, ~20%.

**Goal:** "a dashboard without building a dashboard" (doc 01, sub-problem 8), over data that our own loop produced.

**Pain points addressed:** 5 (lineage made visible). It also delivers the "rules improve" story.

#### 2a. Data
- `/api/studio/rows` reads `transaction_rows(runtime().ledger)`. The column keys are already stable: `lineage_id, vendor, category, action, route, amount, savings, firewall_ms, blocked_reasons, approved_by, status, delivery, invoice_status, payout_net, dispute_win_odds, dispute_outcome`.
- **Three rows make a weak dashboard.** Add `backend/scripts/seed_history.py`. It runs the real step functions in replay over about 30 synthetic mandates (varied budgets, vendors and injected attacks), so every seeded row comes from the real code path, not hand-written data. The UI labels this data "seeded history".
- Add `?run_id=` to `/api/studio/rows` so one run can be viewed alongside the history.
- New `GET /api/runs/{id}/calibration` returns `calibrate()`'s `before`, `after`, `changes` and `trust`.

#### 2b. UI
> Full detail is in [doc 11](11-dashboard-ui-plan.md): data contract §8, custom widgets §9, agent layer §10, tasks UI-2.x.

| Piece | Detail |
|---|---|
| Grid | AG Grid / AG Studio over `/api/studio/rows`. Route column colour-coded. Row click opens the lineage timeline. |
| Lineage timeline | `GET /api/ledger?lineage=…` shows each entry with its stage, kind, `entry_hash` and `prev_hash`. "Chain verified" badge from `/api/ledger/verify`. |
| Custom widgets (3) | Savings vs baseline by vendor and category. Firewall routes over time (auto / approval / blocked). Dispute win rate. KPI tiles from `kpis()`. |
| Studio Agent | Natural-language prompts such as "savings by supplier, highlight blocked attempts" build widgets live. **Read-only:** the Studio agent can't move money. Any action button goes through the API and the firewall. |
| Mandate diff | v1 → v2 side by side: allowlist removals, threshold change, the `parent_digest` link, and the trust scores that caused it |

#### 2c. Tests
- `test_studio_row_columns_are_stable`. Widgets bind to these keys, so a rename should fail CI.
- `test_seed_history_uses_real_firewall` (seeded rows have decision entries in the ledger).

**Risks:** if trial or package problems block AG Studio, fall back to an AG Grid Enterprise trial grid with our own widgets. That loses the natural-language beat but keeps the grid and lineage story.

**Exit:** on screen, a Studio prompt builds a widget from run data and seeded history. Clicking a row opens its lineage timeline. The mandate diff is visible.

> 🟡 **In progress (2026-11-06).**
> - **Done:** 2a seeded history and 2c tests.
>   - `app/seed.py` runs 30 synthetic mandates through the real `runs.step_*` functions in replay. That gives about 60 purchases over 28 days, covering firewall decisions, approvals and rejections, captures, delivery proof, disputes answered by the desk's own recommendation, and stage 10 calibration. The history ledger's hash chain verifies.
>   - `GET /api/studio/rows?history=true` merges it with the current run, each row tagged `source: run | seeded`. `GET /api/studio/history/verify` checks the chain. Run `backend/scripts/seed_history.py` for a summary.
>   - Tests: `test_studio_row_columns_are_stable` freezes `s09_observe.ROW_COLUMNS` and checks the frontend's Studio field ids against it, and `test_seeded_history_comes_from_the_real_code_path` (`tests/test_studio_contract.py`, 6 tests).
> - **Next:** the three custom widgets, the lineage timeline from a grid row, `GET /api/runs/{id}/calibration` and the mandate diff.

**Phase 2 task tracker** (branch `claude/phase-2-studio`)

- [x] Seeded history through the real step functions (`app/seed.py`, `?history=true`)
- [x] Frozen Studio row contract, checked against the frontend (`tests/test_studio_contract.py`)
- [x] Decide: keep the single flat table (decided 2026-11-06). The multi-table model (doc 11 §8) is not needed for the widgets. **Superseded 2026-11-12:** the PayPal pages added more Studio data sources; see the addendum below. The agent's own data is still the one flat `Transactions` table.
- [x] Widget 1: saved vs retail by vendor and category, on captured purchases only (`column-chart-grouped`)
- [x] Widget 2: firewall routes by week (`column-chart-stacked` on `created_at::week`)
- [x] Widget 3: dispute outcomes by supplier (`bar-chart-stacked`, disputed rows only) beside supplier trust (new `supplier_trust` column, same formula as `s10_learn.supplier_trust`; payout attacks unscored)
- [x] KPI tiles: captured spend, saved vs retail (captured), purchases, blocked by the firewall
- [x] Lineage timeline: click a grid row to see its ledger entries with `entry_hash` / `prev_hash` and the chain badge (`GET /api/studio/lineage/{id}`, `LineageDrawer`)
- [x] `GET /api/runs/{id}/calibration` (read-only preview) and the mandate v1 → v2 diff (`GET /api/studio/calibrations` for the seeded history, `MandateDiff` panel)
- [x] Studio Agent natural-language prompts over the data (read-only: it can't move money). Claude Haiku 5.5 through `app/ai_proxy.py` and `src/studio/claudeAdapter.ts`; verified live 2026-11-06: "Add a chart of captured savings by category" ran the orchestrator, Page agent and Widget agent and added the widget
- [x] Exit check: a Studio prompt builds a widget from run plus seeded data, a row opens its lineage, the mandate diff is visible

**Phase 2 addendum (2026-11-12), merged to `main`**

- [x] **PayPal account pages** (`Revenue`, `Receivables`, `Cash`, `Catalogue`), adapted from the hackathon's AG Grid boilerplate. Backend: `app/studio_paypal.py`, `GET /api/studio/paypal` (60 s cache; `?refresh=true` bypasses it, `?fixture=true` forces the fixture). Frontend: `src/studio/paypalReport.ts`. Two data modes: **live** sandbox read, or a fixed **replay fixture** dated 2026-11-05.
- [x] **Failure handling:** a live-read 403 (a missing permission such as Transaction Search) falls back to the fixture with a visible notice; any other failure shows an error with Retry and is never passed off as fixture data. A failed PayPal read never blanks the `Purchases` or `Agent Activity` pages.
- [x] **Agent Activity page** (`#/studio/activity`), derived from the hash-chained ledger rather than an invented agent store: firewall decisions, auto-settled, escalated, average firewall latency, decisions by day and route, latency by route, human escalation outcomes, dispute win odds by supplier, and an escalations and blocked-proposals grid.
- [x] **Agent to PayPal join:** `Transactions.capture_id` is related many-to-one to `PayPal Transactions.id`. Detail drawers open both ways: a capture cell opens the PayPal transaction (with the linked agent purchase), and the lineage drawer links back to its PayPal capture. Invoice rows open an invoice drawer.
- [x] **Host UI:** grouped tabs, the selected page kept in the URL hash (`#/studio/<page>`), arrow-key, Home and End tab navigation, per-page hints, a Live or Replay chip with an "as of" time and Refresh, a loading skeleton, and Retry on failure. Revenue has a currency switch (USD preselected) because invoices are USD or EUR and are not converted.
- [x] **Fix:** `GET /api/studio/lineage/{id}` also resolves rows from the persistent runtime ledger after a restart.
- [ ] Not verified: the live sandbox read has only run against a mock PayPal. Transaction Search was enabled on the sandbox app afterwards, but no live read has been confirmed yet.

---

### Phase 3: Defend + post-purchase ops (Sat Nov 7 – Mon Nov 9). Cluster C ~15%, cluster D ~10%.

**Goal:** close the loop on real PayPal objects where it matters most (disputes), and keep the rest scripted.

**Pain points addressed:** 3, 4, 5, 7, 11. Pain points 6 and 9 stay scripted.

#### 3a. Webhook endpoint (pain point #11)
- New `POST /api/webhooks/paypal`. It reads `await request.body()` **unchanged** and passes the raw body through to verification.
- **Fix in `SandboxPayPal.verify_webhook`:** today it takes a parsed dict. Re-serialising the JSON is the exact cause of `VERIFICATION_FAILURE` in SO #75306849. Build the verification request around the raw body.
- `WebhookInbox` already dedupes by event ID and writes to the ledger. Make it a long-lived singleton, not one per call.
- Dispatch by event type:
  - `CUSTOMER.DISPUTE.CREATED` and `.UPDATED`: build evidence and triage.
  - `PAYMENT.CAPTURE.COMPLETED`: ledger entry.
  - `PAYMENT.PAYOUTSBATCH.*`: payout status.
- Register the Render URL (Phase 4), or a local tunnel for now, as the sandbox webhook. That gives the `PAYPAL_WEBHOOK_ID`.

#### 3b. Defend (pain points #3, #4, #5) — COMPLETED & VERIFIED (2026-11-05)
- **Dispute → Lineage Lookup:** Matched primarily via `disputed_transactions[].custom` (the Orders v2 lineage thread), falling back to `seller_transaction_id` (`capture_id`) in the sealed ledger.
- **8 Deterministic Reason Playbooks (`s08_defend.PLAYBOOKS`):**
  1. *Item Not Received:* Contests if Stage 5 tracking proves delivery (≥85% win odds, +$23 EV); shares tracking if in transit; refunds if unverified. Never demands return of undelivered goods.
  2. *Not As Described:* Enforces sealed return window; defect claims cap odds at 35% and recommend `refund_with_return` with `return_shipping_address` attached.
  3. *Duplicate Charge:* Scans mandate ledger within 48h; refunds duplicates or contests single capture via deterministic `PayPal-Request-Id`.
  4. *Incorrect Amount:* Refunds overcharge difference only or contests exact penny-exact match.
  5. *Refund Not Processed:* Honours prior sealed refund commitments.
  6. *Unauthorised:* Flags security review; contests only with both delivery proof and human approval.
  7. *Recurring / Other Means:* Single capture contests; multiple captures surrender.
  8. *Unknown:* Routes to manual review.
- **Stage-Aware Fee Modeling:** Handling cost scales with risk: **$15** (Inquiry) → **$20** (Chargeback) → **$25** (Arbitration).
- **Carrier Tracking Endpoint (`POST /api/deliveries`):** Seals live carrier tracking (`carrier`, `tracking_number`, `status: DELIVERED`) into `ledger.db` for live sandbox orders, enabling `PROOF_OF_FULFILLMENT`.
- **Outcome Sync to Stage 10:** PayPal claim verdicts (`dispute_outcome`) are recorded as `WON` / `LOST`, updating supplier reliability scores.
- **Endpoints & UI:**
  - `GET /api/disputes` returns active dispute queue with local-time timeline.
  - `GET /api/disputes/{id}` returns assessment, drafts, and facts.
  - `GET /api/disputes/{id}/brief.pdf` generates cryptographic legal PDF evidence brief via ReportLab.
  - `POST /api/disputes/{id}/respond` sends `provide-evidence`, `make-offer`, `send-message`, or `accept-claim` with human confirmation (D-4).
  - `POST /api/deliveries` records live carrier tracking proofs.
  - UI `DisputeDesk.tsx` in Mission Control shows timeline, EV cards, draft editor with optional Claude polish, and 1-click submit.

#### 3c. Pay out (pain point #7)
- If B-2 passed, `release_payout` runs against sandbox Payouts. `sender_batch_id` is lineage-derived, and PayPal rejects a reused one, which adds a second layer of idempotency.
- The fee split (2% + $0.25 in `release_payout`) is an **illustrative assumption**. The UI labels it that way.
- On screen: the payout is blocked without both tokens, then released.

#### 3d. Stages 5 and 6 stay scripted
- **Delivery reports** (stage 5) come from a small "simulate carrier update" control. `reschedule` shows tranche dates moving.
- **Invoice forensics** (stage 6) runs as it does today. The "NW 1001" resubmission is flagged `DUPLICATE` and `PAYEE_MISMATCH`.

#### 3e. Tests
- `test_webhook_endpoint_verifies_raw_body` (replay gateway asserts it received the bytes)
- `test_dispute_maps_to_lineage_by_capture_id`
- `test_provide_evidence_multipart_shape` (replay records the part names and content types)
- `test_payout_endpoint_requires_both_tokens`

**Risks**
| Risk | Fallback |
|---|---|
| The sandbox dispute isn't in an evidence-accepting state by Nov 9 | Show the real dispute ID and status. Submit in replay. The video says so. |
| Payouts returns 403 (B-2) | Stage 7 runs in replay |

**Exit:** `provide-evidence` accepted on the real sandbox dispute, or the fallback has been recorded. The webhook endpoint verifies a real sandbox event. The payout is blocked and then released on screen.

> 🟡 **Partly done early (2026-11-06).** The dispute desk runs live (offers, return acknowledgement, outcome sync). Still open: a live `provide-evidence` submission, the webhook endpoint against a real sandbox event, and the on-screen payout block/release.
>
> **Update (2026-11-12):** the webhook endpoint (`POST /api/webhooks/paypal`, raw-body verification, durable inbox) is built and unit-tested. It has not received a real PayPal event yet.

---

### Phase 4: Deploy & evidence (Mon Nov 9 – Tue Nov 10). Ship, ~15% (shared with Phase 5).

**Goal:** a public URL the judges can open, numbers that back up our claims, and honest sponsor write-ups.

#### 4a. Render
- **One web service.** FastAPI serves the built frontend (`frontend/dist` mounted with `StaticFiles`). Frontend and API share an origin, so the localhost-only CORS rule in `main.py` doesn't need loosening.
- Add a `render.yaml` blueprint:
  - Build: `pip install -r backend/requirements.txt` and `npm ci && npm run build` in `frontend/`.
  - Start: `uvicorn app.main:app --workers 1` (run state is in process).
- **Ledger persistence.** Render's filesystem is ephemeral. Either seed the history at boot (`seed_history.py`) and keep live runs in a per-boot SQLite file, or attach a persistent disk. Seeding at boot is enough for judging.
- **Environment:** a long random `GATE_SECRET`. `REPLAY_MODE` defaults to `true` on the public URL, so judges can't spend our sandbox, and the README explains how to run live.
- **Render Workflows** only if the negotiation fan-out fits naturally. Don't contort the design for a $1k credit prize.

#### 4b. APIMatic (pain point #12)
Use the Context Plugin while writing Phases 1–3. Record which payloads it checked: Orders create and capture, Payouts batch, Disputes multipart, and webhook verify. That record becomes the README section "How we used APIMatic". It must be accurate: the judge for this prize is APIMatic's co-founder.

#### 4c. Evaluation harness, `backend/eval/`
| Script | Measures | Target (doc 07) |
|---|---|---|
| `firewall_cases.py` | 50 scenarios (over budget, non-refundable, off-allowlist, injected, review-first, prior spend) → route | 100% of over-budget, non-refundable and injected cases are not auto-settled |
| `negotiation_runs.py` | 20 runs with varied seller parameters → savings vs baseline, turns, schema drops | 12–18% savings within 3 turns. No malformed offer survives the gate. |
| `idempotency_runs.py` | N retries per operation → count of real side effects | Exactly 1 per operation |

The output is a Markdown table pasted into the README. These numbers back up the pitch's claims.

#### 4d. README
Rewrite for judges: what it is, a live URL, a 3-step local run, architecture, a sponsor-usage section per tool, the evaluation table, and what's simulated vs live.

#### 4e. UI polish sweep
No new layouts in this phase. Run doc 11's UI-4 tasks against the checklist in doc 11 §13.

**Exit:** the public URL runs the arc. The evaluation table is in the README. **Feature freeze Tuesday Nov 10 at 18:00.**

**Phase 4 status (2026-11-06):**
- [x] 4a Render files: `Dockerfile`, `render.yaml`, `FRONTEND_DIST` static serving, CORS from settings, single worker. Verified locally as one process. [ ] The service itself is not created yet (needs the Render account, B-7).
- [ ] 4b APIMatic: not started and not claimed anywhere (needs the account, B-7). The README says so.
- [x] 4c Evaluation harness `backend/eval/` with `RESULTS.md`, also run as tests. It found paraphrased prompt injection slipping past the regex tripwire; the patterns were widened using the dev phrases only and the held-out catch rate (1 of 5) is reported as a known gap.
- [x] 4d README rewritten for judges. [ ] Add the live URL after deploying.
- [~] 4e UI polish sweep: largely done for the Command Center (formats, grouped tabs, hints, provenance chip, loading and error states, drawers, keyboard navigation). Not covered: the Mission Control screens, narrow-viewport checks and dark mode.

---

### Phase 5: Video & submit (Tue Nov 10 – Wed Nov 11)

- **Present mode:** doc 11 UI-5.1 (hotkeys, larger type, Studio in view mode).
- **Script:** start from doc 08's 3-minute script, re-timed to the real screens. Keep the beats: hook (Issue #95) → discovery and negotiation → firewall (auto / approve / attack) → dispute defended from the seal → AG Studio → close.
- **Recording:** record in **replay mode** so every take is identical. Cut in one clip of the real sandbox order ID and the real dispute response as proof of live integration.
- **Devpost:** description, sponsor tools used (each matching the README), repo link, video link. Check the rules for repo visibility (the repo is private now) and video length before uploading.
- **Submit on Wednesday Nov 11.** Thursday Nov 12 before 12:00 PM PST is buffer only.

---

## 5. Risk register

| # | Risk | Likelihood | Impact | Mitigation / fallback |
|---|---|---|---|---|
| R1 | AUTO_SETTLE can't capture without a buyer popup (B-9) | Medium | Medium | Popup path, stated honestly. The firewall story is unaffected. |
| R2 | Payouts disabled in the sandbox (B-2) | Medium | Low | Stage 7 runs in replay. It was always cluster D. |
| R3 | Sandbox dispute stuck before it accepts evidence (B-4) | Medium | Medium | Opened on day 1. Replay submit with a real dispute ID shown. |
| R4 | Channel3 shape, credits or missing return terms | Medium | Medium | Replay catalog. Labelled return-policy table. |
| R5 | AG Studio trial or package friction | Low–Medium | High (AG Grid prize) | Started in Phase 0. AG Grid Enterprise fallback. |
| R6 | Phase 1 runs over | Medium | High | Hard stop Nov 5. Phase 2 starts Nov 3 on replay. |
| R7 | An unverified citation appears in the video | Low | High (credibility) | Phase 0 source check |
| R8 | Render restart wipes run state | Medium | Low | Seeded at boot. Single worker. |

---

## 6. Backlog: carried forward

Open items from later phases, kept here so they aren't lost while Phase 2 runs. Pick them up in Phase 3 or 4.

- [ ] **Live `provide-evidence` submission.** Multipart, with the PDF brief, on a real sandbox dispute. Only the replay double has received it so far.
- [ ] **Webhook signature verification against a real sandbox event.** The endpoint (`POST /api/webhooks/paypal`) verifies against the raw bytes, de-duplicates through the ledger and is unit-tested, including that the received bytes are spliced into the verify request untouched. Still open: a real PayPal event. It needs the deployed URL registered as a webhook in the sandbox app, and `PAYPAL_WEBHOOK_ID` set (pain point #11).
- [ ] **On-screen payout block and release.** Stage 7 payout without the VERIFIED and RECONCILED gate tokens is refused, then released. It's proven in tests and the demo arc, but not shown in the UI.
- [ ] **Live PayPal account read.** `GET /api/studio/paypal` against the real sandbox account has only run against a mock. Enable Transaction Search on the sandbox app, restart the backend, click Refresh and confirm the chip turns green; then update the README. The sandbox merchant currently has no products, plans or invoices, so Revenue, Receivables and Catalogue will be empty live unless it is seeded.
- [x] **Agent-to-PayPal reconciliation page (2026-11-12).** `app/studio_reconcile.py` derives one row per captured agent purchase from the `capture_id` join, plus PayPal purchase captures the agent never decided; `GET /api/studio/reconciliation`, `src/studio/reconcileReport.ts`. Statuses: Matched, Amount mismatch, Pending (captured within 3 h; Transaction Search may lag), Outside window (older than 31 days), Unsettled, Simulated (seeded or replay: no PayPal object), Not decided by agent. The replay fixture includes one such orphan (`TXN-FIXT-0007`). Tests: `tests/test_studio_reconcile.py`. The live status logic is covered by unit tests only, not by a live sandbox read.
- [ ] **Command Center loose ends:** the Revenue invoice-date filter has no default period (Studio 3.0 does not apply a relative date filter from saved state on load); Mission Control narrow-viewport and dark-mode checks.
- [ ] **Licence for the boilerplate.** The README credits `paypaldev/hackathon-paypal-ag-grid-boilerplate`, which has no licence file. A person should confirm the wording.
- [ ] `backend/eval/firewall_cases.py` and `backend/eval/run_all.py` fail `ruff format --check`; they were that way before the Command Center work.
- [ ] **Stages 6, 7 and 10 are still scripted.** Invoice forensics, payout release and calibration run in replay and seeded history, not on live sandbox objects.

## 7. What we are not building

| Cut | Why |
|---|---|
| Bryntum Gantt / Scheduler | A third UI framework for a $1k prize. `s05_verify.reschedule` is the Gantt-lite stand-in. |
| Slack or Zapier approvals | The in-app approval card shows the same idea |
| Auth or multi-tenancy | The demo starts in a pre-seeded workspace (doc 08) |
| Real PDF or OCR invoice parsing | Stage 6's point is forensics, not extraction |
| LLM-priced negotiation | Money stays deterministic. The LLM may only draft seller *messages*. |
| SaaS sprawl (pain point #10) | Outside the loop |

---

## 8. Team split (3 people)

| Person | Phase 0 | Phase 1 | Phase 2 | Phase 3 | Phases 4–5 |
|---|---|---|---|---|---|
| **A: Payments** | B-1, B-2, B-4, B-9 | Run-session API, prepare/capture, live Orders | Calibration endpoint, seed script | Webhook endpoint, live dispute, live payout | Render, evaluation harness |
| **B: Frontend** | Frontend scaffold, routing | Mandate form, arena, firewall drawer, PayPal button, timeline | Lineage timeline, mandate diff | Dispute card, payout view | Demo polish, recording |
| **C: Data & sponsors** | B-5, B-6, B-7, source check | Live Channel3 | AG Studio grid, widgets, Studio Agent | Optional LLM dispute narrative | APIMatic write-up, README, video edit |

If you're working solo, run the phases in order. Drop Phase 3's live payout first, then the Studio Agent's natural-language beat (keeping the grid), before touching Phase 1 scope.
