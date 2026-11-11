# Section 12: Final Sprint Execution Plan & Multi-Agent MR Blueprint

> **As of:** 2026-11-12 (built on `main` @ `e6806f7`).
> **Purpose:** Self-contained engineering specification synthesizing all findings from the backend guarantee probe, the live PayPal Sandbox Transaction Search verification, the AG Studio Command Center audit, and the submission readiness review.
> **How to use this document:** Work is partitioned into **5 focused, sequential Merge Requests (MR 1 → MR 5)** with non-overlapping file ownership where possible, exact file and line references, data schemas, code blueprints, and verification commands so autonomous agents can execute each MR cleanly.

---

## 1. Executive Synthesis of Findings

### 1.1 Confirmed Core Guarantee Bugs (Reproduced via Probe Against Step Functions)

| ID | Headline Guarantee Violated | Root Cause (Exact File & Lines) | Impact |
|---|---|---|---|
| **BUG-1** | **Mandate budget cannot be overspent** | `Runtime.spent(mandate_lid)` ([`backend/app/orchestrator.py:52-53`](../backend/app/orchestrator.py#L52-L53)) sums only `capture` entries, and `s03_govern.evaluate()` ([`backend/app/stages/s03_govern.py:68`](../backend/app/stages/s03_govern.py#L68)) checks `spent + total <= mandate.budget` only once at govern time. Neither `step_prepare_order()` ([`backend/app/runs.py:230-251`](../backend/app/runs.py#L230-L251)) nor `s04_settle.prepare_order()` ([`backend/app/stages/s04_settle.py:25-86`](../backend/app/stages/s04_settle.py#L25-L86)) re-checks remaining budget before creating/sealing the PayPal order. | Two items that each fit within a `$1,500` budget at govern time (e.g. `$1,020` and `$590`, both routed to `HUMAN_APPROVAL`) can both be approved and captured for **`$1,610` total** (`$110` over the mandate budget). |
| **BUG-2** | **Every need produces an isolated, deterministic lineage** | In `step_discover_and_negotiate()` ([`backend/app/runs.py:146`](../backend/app/runs.py#L146)), every negotiated need computes `lid = txn_lineage(mlid, need.category, "bulk")`. Direct needs use `c.sku` as the 3rd part, which is unique per product, but negotiated needs hardcode `"bulk"`. | Two negotiated needs in the same `need.category` (e.g. two `"monitors"` needs) produce the exact same `lineage_id` and silently overwrite `run.items[item.lineage_id]` (2 needs in, 1 item out). |
| **BUG-3** | **Tamper-evident ledger detects deletion & truncation** | `EvidenceLedger.verify()` ([`backend/app/core/ledger.py:91-103`](../backend/app/core/ledger.py#L91-L103)) iterates `SELECT * FROM entries ORDER BY seq` and recomputes unkeyed SHA-256 links (`prev_hash` → `entry_hash`). While SQLite triggers block in-connection `UPDATE`/`DELETE`, an attacker with file access to `ledger.db` can drop the `no_delete` trigger and delete tail rows `seq > k` (or rewrite rows from `GENESIS`). | Truncating the newest entries (e.g. deleting a `capture`, `rejection`, or `webhook` row from the tail of `ledger.db`) still returns `verify() == (True, None)` because nothing records a keyed HMAC checkpoint of the chain head `(seq, entry_hash)`. |

### 1.2 Live PayPal Sandbox Transaction Search Verification (Confirmed Live)

Transaction Search (`/v1/reporting/transactions`) and Balances (`/v1/reporting/balances`) are now **enabled and verified** on the configured sandbox merchant account:
- **Live query result:** `94` transactions returned in the last 31 days; `2` currency balances (`USD`, `EUR`).
- **Live `capture_id` join confirmed:** All 3 real sandbox captures stored in `ledger.db` (`79H28497XC211214U` for `$28.00`, `8BR25737S32734541` for `$49.99`, `3MT57171KG6470404` for `$28.00`) appear in `/v1/reporting/transactions` with matching `transaction_id == capture_id`.
- **Three live-vs-fixture discrepancies uncovered during live inspection:**
  1. **Event codes:** In live PayPal Sandbox, saved-wallet (`vault_id`) captures use event code **`T0003`** (*PreApproved Payment Bill User Payment*), whereas JS SDK buyer-approval captures use **`T0006`** (* Express Checkout Payment*). Currently, `_EVENT_TYPES` in [`backend/app/studio_paypal.py:104`](../backend/app/studio_paypal.py#L104) only maps `T0001`, `T0006`, `T1105`, and `T1503`, leaving 6 live sandbox event codes (`T0003`, `T0200`, `T1107`, `T1110`, `T1111`, `T1900`) unlabelled as raw codes in the UI.
  2. **Subject vs. note:** Live Orders v2 captures populate `transaction_info.transaction_subject` (e.g. `"1080P HD Webcam"`, `"USB Condenser Microphone"`) rather than `transaction_note`, while dispute refunds (`T1107`) populate `transaction_note` (`"Dispute refund"`). `_transaction_rows()` ([`backend/app/studio_paypal.py:296`](../backend/app/studio_paypal.py#L296)) currently reads only `t.get("transaction_note")`.
  3. **Sign convention on captures:** In live mode, the sandbox credentials belong to the merchant account receiving the order capture (`+28.00` gross, `-1.25` fee), whereas `_fixture_capture` in replay ([`backend/app/studio_paypal.py:446`](../backend/app/studio_paypal.py#L446)) records `-118.00`. Any reconciliation comparison between `StudioRow.amount` (always positive) and `paypalTransactions.amount` must compare `Number(purchase.amount)` against `Math.abs(Number(paypalTxn.amount))` so both live and replay modes reconcile identically.
  4. **Natural orphan captures in live mode:** Live Transaction Search contains historical sandbox captures (`17M15909JK373804U` `$1,020.00`, `6ET18262NT9758442` `$49.99`, `6LS15366RB338544E` `$28.00`) from earlier test runs that are not in the cleaned 20-entry `ledger.db`. On the new **Reconciliation** page, these naturally surface as real `ORPHAN` captures (PayPal settled money with no matching agent mandate in the active ledger).

### 1.3 Security, Product & Submission Gaps

1. **Live-mode security hardening:**
   - [`backend/app/config.py:17`](../backend/app/config.py#L17) defaults `gate_secret` to `"dev-only-gate-secret-change-me"` even when `replay_mode=False`.
   - [`backend/app/ai_proxy.py:28-58`](../backend/app/ai_proxy.py#L28-L58) uses an unbounded `_hits: dict[str, deque[float]]` keyed by spoofable `X-Forwarded-For`, allowing memory growth or rate-limit bypass if `X-Forwarded-For` is rotated.
   - `.env.example` sets `LLM_MODEL=claude-opus-5-5` instead of `claude-haiku-4-5-20251001`.
2. **Command Center Reconciliation & Agent Activity depth:**
   - The `capture_id` join is in place, but there is no dedicated **Reconciliation** page (`#/studio/reconciliation`) classifying captures into `MATCHED`, `AMOUNT_MISMATCH`, `UNSETTLED` (in agent ledger, missing in PayPal), and `ORPHAN` (in PayPal, missing in agent ledger), nor surfacing Total Fees and Net Cash KPIs.
   - `CommandCenter.tsx` places non-tab `<span role="presentation">` group labels inside `<div role="tablist">`, violating ARIA `tablist` child rules, and hardcodes `"sub-ms latency"` in the `Agent Activity` hint instead of computing it from `rows`.
3. **Mission Control Stages 5–7 & Editable Needs:**
   - Stages 5 (`s05_verify.verify_delivery`), 6 (`s06_reconcile.InvoiceForensics.check`), and 7 (`s07_payout.release_payout`) only run inside `run_demo()` and seeded history; a judge using Mission Control (`#/`) cannot see a supplier payout refused without `VERIFIED` + `RECONCILED` tokens and then released with Payouts v1.
   - `MandateForm.tsx` edits mandate thresholds and allowlists, but does not let the user edit or add procurement `needs` (always falling back to the 3 hardcoded `DEMO_NEEDS` in `backend/app/runs.py:37-41`).
4. **Prompt-injection paraphrase gap:**
   - `backend/eval/firewall_cases.py` documents a 1-of-5 catch rate on held-out paraphrased prompt injections (`RESULTS.md`) because `s03_govern.py` uses regex tripwires only. Adding an optional, **escalate-only** structured LLM classifier (`LLM.structured`) when regex passes closes this gap without ever permitting the LLM to downgrade a block or numeric failure.

---

## 2. MR Roadmap & Execution Order

Execute these 5 MRs in order. Each MR is small, self-contained, and leaves `pytest`, `ruff`, `oxlint`, and `tsc -b && vite build` green.

| MR | Branch Name | Scope | Primary Files Touched | Est. Effort |
|---|---|---|---|---|
| **MR 1** | `fix/core-guarantees-and-security` | Fix BUG-1 (budget overspend), BUG-2 (negotiated category collision), BUG-3 (HMAC ledger head checkpoint); harden live `GATE_SECRET` & `ai_proxy` rate limiter; format eval files | `backend/app/stages/s04_settle.py`, `backend/app/runs.py`, `backend/app/orchestrator.py`, `backend/app/core/ledger.py`, `backend/app/core/errors.py`, `backend/app/config.py`, `backend/app/ai_proxy.py`, `backend/tests/test_runs.py`, `backend/tests/test_ledger_and_firewall.py` | ~1.5 hrs |
| **MR 2** | `feat/studio-reconciliation-and-live-join` | Expand live PayPal event codes (`T0003`, `T1107`, etc.) & `transaction_subject` fallback; add fixture reconciliation cases; build `#/studio/reconciliation` page (`MATCHED`, `AMOUNT_MISMATCH`, `UNSETTLED`, `ORPHAN`, fee/net KPIs); fix `tablist` ARIA & dynamic latency hint | `backend/app/studio_paypal.py`, `frontend/src/studio/paypalReport.ts`, `frontend/src/studio/CommandCenter.tsx`, `frontend/src/studio/ai.ts`, `backend/tests/test_studio_paypal.py`, `backend/tests/test_studio_contract.py` | ~2.5 hrs |
| **MR 3** | `feat/sandbox-seeder-and-live-verification` | Add idempotent `backend/scripts/seed_paypal_sandbox.py` (Products, Plans, Invoices in Sandbox); update `README.md` and `docs/09`–`11` with verified live Transaction Search join results | `backend/scripts/seed_paypal_sandbox.py`, `backend/tests/test_studio_paypal.py`, `README.md`, `docs/09-implementation-framework.md`, `docs/10-execution-plan.md`, `docs/11-dashboard-ui-plan.md` | ~1.5 hrs |
| **MR 4** | `feat/mission-control-stages-5-to-7-and-editable-needs` | Surface Stages 5–7 (Delivery Verify → 3-Way Invoice Forensics → Dual-Token Payout Gate) interactively on settled cards in Mission Control; make `needs` editable in `MandateForm.tsx` | `backend/app/runs.py`, `backend/app/api.py`, `frontend/src/api/client.ts`, `frontend/src/features/deal/DealCard.tsx`, `frontend/src/features/mandate/MandateForm.tsx`, `frontend/src/App.tsx`, `backend/tests/test_runs.py` | ~2.5 hrs |
| **MR 5** | `feat/escalate-only-injection-classifier-and-deploy` | Optional escalate-only LLM injection guard in `s03_govern.py`; re-run `backend/eval/run_all.py` and update `RESULTS.md`; verify `render.yaml` & webhook dispatch | `backend/app/stages/s03_govern.py`, `backend/eval/firewall_cases.py`, `backend/eval/RESULTS.md`, `render.yaml`, `README.md` | ~1.5 hrs |

---

## 3. Detailed MR Specifications

---

### MR 1: `fix/core-guarantees-and-security`

#### 1A. Fix BUG-1 — Prevent Budget Overspend Across Concurrent Human Approvals

- **Files:**
  - [`backend/app/core/errors.py`](../backend/app/core/errors.py)
  - [`backend/app/stages/s04_settle.py`](../backend/app/stages/s04_settle.py) (lines 25–50)
  - [`backend/app/runs.py`](../backend/app/runs.py) (lines 230–251)
  - [`backend/app/orchestrator.py`](../backend/app/orchestrator.py) (lines 52–56)
- **Specification:**
  1. In `backend/app/core/errors.py`, add `class BudgetExceeded(GuardViolation): code = "BUDGET_EXCEEDED"`.
  2. In `backend/app/orchestrator.py`, add a helper `Runtime.committed_spend(mandate_lid: str) -> Decimal` (or `EvidenceLedger.committed_spend(mandate_lid: str) -> Decimal`) that sums the amount of every lineage under `mandate_lid:` that has **either** a `capture` entry **or** an uncaptured `seal` entry (so an order that has been prepared/sealed and is awaiting buyer approval reserves its budget immediately and cannot be raced by a second `/prepare` call):
     ```python
     def committed_spend(self, mandate_lid: str) -> Decimal:
         prefix = f"{mandate_lid}:"
         by_lid: dict[str, Decimal] = {}
         for e in self.ledger.entries():
             if not e.lineage_id.startswith(prefix):
                 continue
             if e.kind == "seal":
                 by_lid[e.lineage_id] = Decimal(str(e.payload["amount"]))
             elif e.kind == "capture":
                 by_lid[e.lineage_id] = Decimal(str(e.payload["amount"]["value"]))
             elif e.kind in ("capture_failed", "rejection"):
                 by_lid.pop(e.lineage_id, None)
         return sum(by_lid.values(), Decimal("0"))
     ```
  3. In `backend/app/stages/s04_settle.py:prepare_order()`, accept optional keyword arguments `mandate_budget: Decimal | None = None` and `committed_spend: Decimal = Decimal("0")`. Right after building `pu = build_purchase_unit(...)` (line 48), enforce:
     ```python
     order_total = Decimal(pu["amount"]["value"])
     if mandate_budget is not None and committed_spend + order_total > mandate_budget:
         raise BudgetExceeded(
             f"order {order_total} + committed spend {committed_spend} exceeds mandate budget {mandate_budget}",
             lineage_id=lid,
             order_total=str(order_total),
             committed_spend=str(committed_spend),
             budget=str(mandate_budget),
         )
     ```
  4. In `backend/app/runs.py:step_prepare_order()` (line 230), compute `committed = rt.committed_spend(run.mandate_lineage)` (excluding `lineage_id` if retrying the same order) and pass `mandate_budget=run.mandate.budget, committed_spend=committed` into `s04_settle.prepare_order(...)`. Also expose `committed_spend` in `Run.snapshot()` alongside `spent`.

#### 1B. Fix BUG-2 — Prevent Negotiated Need Category Lineage Collision

- **File:** [`backend/app/runs.py`](../backend/app/runs.py) (lines 126–170)
- **Specification:**
  1. In `step_discover_and_negotiate()`, count how many negotiated needs share each `need.category`, or derive a deterministic slug when a category appears more than once:
     - If a category appears **once** among negotiated needs (the default 3-need demo), keep `subject = "bulk"` so all existing replay IDs, seeded history lineages, and tests remain 100% unchanged.
     - If a category appears **more than once** among negotiated needs in the same run, set `subject = f"bulk-{idx}-{sha256_hex(need.description)[:6]}"` (for the 2nd+ occurrence, or all occurrences when duplicated) so `txn_lineage(mlid, need.category, subject)` is guaranteed unique per need.

#### 1C. Fix BUG-3 — Keyed HMAC Checkpoint Against Ledger Truncation

- **File:** [`backend/app/core/ledger.py`](../backend/app/core/ledger.py) (lines 14–108)
- **Specification:**
  1. Add a single-row table `ledger_head` to `DDL` in `backend/app/core/ledger.py`:
     ```sql
     CREATE TABLE IF NOT EXISTS ledger_head (
         id INTEGER PRIMARY KEY CHECK (id = 1),
         seq INTEGER NOT NULL,
         entry_hash TEXT NOT NULL,
         mac TEXT NOT NULL
     );
     ```
  2. Accept an optional `secret: str = ""` parameter in `EvidenceLedger.__init__(self, path: str = ":memory:", secret: str = "")` (defaulting to `settings.gate_secret` when instantiated via `Runtime`).
  3. Define `_head_mac(self, seq: int, entry_hash: str) -> str`:
     ```python
     return hmac.new(self._secret.encode("utf-8"), f"{seq}:{entry_hash}".encode("utf-8"), hashlib.sha256).hexdigest()
     ```
  4. Inside `EvidenceLedger.append()`, within the same `with self._lock, self._conn:` transaction that inserts into `entries`, fetch the newly assigned `seq = cur.lastrowid` and upsert `ledger_head`:
     ```sql
     INSERT INTO ledger_head(id, seq, entry_hash, mac) VALUES (1, ?, ?, ?)
     ON CONFLICT(id) DO UPDATE SET seq = excluded.seq, entry_hash = excluded.entry_hash, mac = excluded.mac
     ```
  5. Inside `EvidenceLedger.verify()`:
     - Run the existing row-by-row `prev_hash` and `entry_hash` check first.
     - Then read `SELECT seq, entry_hash, mac FROM ledger_head WHERE id = 1`.
     - If `ledger_head` has a row:
       - If `entries` is empty (`prev == GENESIS`), return `(False, 1)` (all rows were truncated).
       - If the last row's `r["seq"] != head["seq"]` or `r["entry_hash"] != head["entry_hash"]`, return `(False, head["seq"])` (tail truncation detected).
       - If `self._secret` is set and `not hmac.compare_digest(head["mac"], self._head_mac(head["seq"], head["entry_hash"]))`, return `(False, head["seq"])` (checkpoint MAC forged).
  6. Update `ledger.db` / `backend/ledger.db` initialization (or backfill `ledger_head` on first open if `entries` exist and `ledger_head` is empty) so existing cleaned databases verify seamlessly.

#### 1D. Live-Mode Security Hardening & Housekeeping

- **Files:**
  - [`backend/app/config.py`](../backend/app/config.py)
  - [`backend/app/ai_proxy.py`](../backend/app/ai_proxy.py)
  - [`.env.example`](../.env.example)
  - [`backend/eval/firewall_cases.py`](../backend/eval/firewall_cases.py), [`backend/eval/run_all.py`](../backend/eval/run_all.py)
- **Specification:**
  1. **`config.py`:** Add a `validate_live_security()` method (or Pydantic `@model_validator(mode="after")`) that raises `ValueError("GATE_SECRET must be changed from the default value when REPLAY_MODE=false")` if `not self.replay_mode and self.gate_secret == "dev-only-gate-secret-change-me"`. (Update `.env` if needed before running in live mode.)
  2. **`ai_proxy.py`:**
     - Cap `_hits` at `MAX_TRACKED_CLIENTS = 1024`; before inserting a new client key, evict expired windows (`not window or now - window[-1] > RATE_WINDOW_S`) and, if still at capacity, pop the oldest key (`next(iter(_hits))`).
     - In `_client_id(request: Request)`, only trust `x-forwarded-for` when `request.client.host in ("127.0.0.1", "::1", "localhost")` or behind Render's proxy (using the **rightmost** untrusted IP or `request.client.host` fallback so a direct client cannot spoof arbitrary `X-Forwarded-For` values to bypass the rate limit).
  3. **`.env.example`:** Change `LLM_MODEL=claude-opus-5-5` to `LLM_MODEL=claude-haiku-4-5-20251001`.
  4. **Formatting:** Run `backend/.venv/bin/ruff format backend/eval/firewall_cases.py backend/eval/run_all.py`.

#### 1E. Required Tests for MR 1
- `test_concurrent_human_approvals_cannot_exceed_budget` in `backend/tests/test_runs.py`:
  - Create a run with `budget=1500` and two needs whose offers total `$1,020` and `$590` (both `HUMAN_APPROVAL`).
  - Approve both decisions.
  - Prepare and capture the `$1,020` order → succeeds (`spent == 1020`).
  - Call `step_prepare_order` on the `$590` order → raises `BudgetExceeded` (`HTTP 409` via API), proving total spend cannot exceed `$1,500`.
- `test_two_negotiated_needs_in_same_category_do_not_collide` in `backend/tests/test_runs.py`:
  - Pass two `"monitors"` needs with `mode="negotiate"` to `start_run`. Assert `len(run.items) == 2` and their `lineage_id`s are distinct.
- `test_ledger_truncation_detected_by_verify` in `backend/tests/test_ledger_and_firewall.py`:
  - Append 4 entries to a file-backed `EvidenceLedger`, drop `no_delete` trigger via raw `sqlite3.connect`, delete `WHERE seq = 4`, and assert `ledger.verify() == (False, 4)`.

---

### MR 2: `feat/studio-reconciliation-and-live-join`

#### 2A. Expand Live PayPal Event Codes, Note Fallback & Reconciliation Fixture Rows

- **File:** [`backend/app/studio_paypal.py`](../backend/app/studio_paypal.py)
- **Specification:**
  1. Update `_EVENT_TYPES` (line 104) to cover all 10 event codes observed in the live PayPal Sandbox account:
     ```python
     _EVENT_TYPES = {
         "T0001": "Payout",
         "T0003": "Vault purchase capture",
         "T0006": "Purchase capture",
         "T0200": "Currency conversion",
         "T1105": "Hold released",
         "T1107": "Dispute refund",
         "T1110": "Dispute hold",
         "T1111": "Dispute hold cancelled",
         "T1503": "Payout hold",
         "T1900": "Balance adjustment",
     }
     ```
  2. In `_transaction_rows()` (line 296), fall back `note` to `transaction_subject` so live Orders v2 captures show their item description:
     ```python
     "eventCode": code,
     "note": t.get("transaction_note") or t.get("transaction_subject"),
     ```
  3. In `fixture_account()` (lines 591–612), ensure the replay fixture exercises every reconciliation state against the seeded history (`CAP-000064` `$118.00`, `CAP-000062` `$178.00`, `CAP-000060` `$1,323.00`, etc.):
     - Keep `CAP-000064` (`$118.00`) and `CAP-000062` (`$178.00`) as exact **`MATCHED`** captures.
     - Add or adjust one fixture capture (e.g. `CAP-000060` with PayPal gross `1350.00` vs agent ledger `1323.00`, or a dedicated `CAP-000055` row) to demonstrate **`AMOUNT_MISMATCH`**, or add an **`ORPHAN`** capture (`CAP-ORPHAN-0091`, `$240.00`, `T0006`, `"Manual checkout outside PactGuard"`) that has no agent ledger row, while the remaining seeded `CAPTURED` rows without a fixture PayPal row demonstrate **`UNSETTLED`**. Recompute the fixture `ending_balance` column so running balances stay consistent.

#### 2B. Build the Agent-to-PayPal `Reconciliation` Page (`#/studio/reconciliation`)

- **Files:**
  - [`frontend/src/studio/paypalReport.ts`](../frontend/src/studio/paypalReport.ts)
  - [`frontend/src/studio/CommandCenter.tsx`](../frontend/src/studio/CommandCenter.tsx)
  - [`frontend/src/studio/ai.ts`](../frontend/src/studio/ai.ts)
- **Data Contract (`ReconciliationRow`):**
  Build a pure function `buildReconciliationRows(purchases: StudioRow[], paypalTxns: Record<string, unknown>[]): ReconciliationRow[]` in `paypalReport.ts` (or a new `frontend/src/studio/reconciliation.ts`):
  ```ts
  export type ReconciliationStatus = 'MATCHED' | 'AMOUNT_MISMATCH' | 'UNSETTLED' | 'ORPHAN'

  export type ReconciliationRow = {
    id: string                 // capture_id or lineage_id
    capture_id: string | null  // PayPal transaction / capture ID
    lineage_id: string | null  // Agent lineage_id (null for ORPHAN)
    order_id: string | null
    date: string | null
    vendor: string
    category: string | null
    route: string | null
    status: ReconciliationStatus
    agent_amount: number | null   // Sealed amount in agent ledger (USD)
    paypal_gross: number | null   // |PayPal transaction amount| (USD)
    paypal_fee: number | null     // |PayPal fee| (USD, positive for display)
    paypal_net: number | null     // paypal_gross - paypal_fee
    delta: number                 // (paypal_gross ?? 0) - (agent_amount ?? 0)
    note: string | null
  }
  ```
- **Matching Rules (Works Identically in Both Live & Replay Mode):**
  1. Filter `paypalTxns` to capture events: `eventType in ('Purchase capture', 'Vault purchase capture', 'T0003', 'T0006')` (or `id` referenced by a purchase's `capture_id`).
  2. For each `StudioRow` where `status === 'CAPTURED'` (or `capture_id != null`):
     - Look up `paypalTxn` by `txn.id === row.capture_id`.
     - If found: let `agentAmt = round2(row.amount)`, `ppGross = round2(Math.abs(Number(txn.amount)))`, `ppFee = round2(Math.abs(Number(txn.fee)))`, `ppNet = round2(ppGross - ppFee)`.
       - Status is `'MATCHED'` if `Math.abs(ppGross - agentAmt) < 0.01`, else `'AMOUNT_MISMATCH'`.
     - If not found in `paypalTxns`:
       - Status is `'UNSETTLED'` (`agent_amount = row.amount`, `paypal_gross = null`, `delta = -row.amount`).
  3. For each capture `paypalTxn` whose `id` was **not** matched to any `StudioRow.capture_id`:
     - Emit an `'ORPHAN'` row (`lineage_id = null`, `vendor = String(txn.counterparty ?? 'Unattributed PayPal capture')`, `agent_amount = null`, `paypal_gross = Math.abs(Number(txn.amount))`, `delta = Math.abs(Number(txn.amount))`).
- **Studio Page Layout (`reconciliationPage` in `paypalReport.ts` / `CommandCenter.tsx`):**
  - **Tab placement:** Under the `Agent` tab group in `CommandCenter.tsx`: `Purchases`, `Agent Activity`, `Reconciliation` (`#/studio/reconciliation`).
  - **KPIs (row 1):**
    1. `Matched spend` (`sum(agent_amount)` where `status == 'MATCHED'`, `currencyFormat`)
    2. `PayPal fees` (`sum(paypal_fee)`, `currencyFormat`)
    3. `Net settled` (`sum(paypal_net)`, `currencyFormat`)
    4. `Exceptions` (`count(id)` where `status != 'MATCHED'`)
  - **Charts (row 2):**
    1. `Reconciliation status breakdown` (`bar-chart` or `pie-chart`: count & amount by `status`)
    2. `Gross vs net settled by capture` (`column-chart-grouped`: `agent_amount`, `paypal_gross`, `paypal_net` on matched/mismatched rows)
  - **Grid (row 3):**
    - `Reconciliation ledger & exceptions` (`grid` over `reconciliation`, sorted by `status` then `date desc`, showing `status`, `capture_id`, `vendor`, `route`, `agent_amount`, `paypal_gross`, `paypal_fee`, `paypal_net`, `delta`, `lineage_id`, `note`).
    - Clicking a row with a `capture_id` in `paypalTxns` opens `PaypalDetailDrawer` (which links to `LineageDrawer`); clicking an `UNSETTLED` row opens `LineageDrawer` directly.

#### 2C. Accessibility, Dynamic Latency Hint & Agent Activity Polish

- **File:** [`frontend/src/studio/CommandCenter.tsx`](../frontend/src/studio/CommandCenter.tsx)
- **Specification:**
  1. **Fix `role="tablist"` structure:** Move the group label (`Agent` / `PayPal account`) outside a `role="tablist"` container or wrap each group's buttons in their own `<div role="group" aria-label={group.label}>` inside `<div role="tablist" aria-label="Command Center pages">` so every direct interactive child is a valid `role="tab"`, with zero bare `<span>` elements directly under `tablist` (or place the group label in a sibling `<span>` outside the inner `role="tablist"`).
  2. **Dynamic latency in `Agent Activity` hint:** Compute `const avgMs = rows.length ? (rows.reduce((s, r) => s + r.firewall_ms, 0) / rows.length).toFixed(2) : '0.00'` and render `avg ${avgMs} ms firewall latency` instead of static `"sub-ms latency"`.
  3. **Add prompt starters in `frontend/src/studio/ai.ts`:** Include `"Which captures have reconciliation exceptions or orphan PayPal settlements?"` and `"Compare gross agent spend vs net PayPal settlement after fees"`.

#### 2D. Required Tests for MR 2
- `test_event_types_cover_live_sandbox_codes` in `backend/tests/test_studio_paypal.py`: Assert `T0003`, `T0200`, `T1107`, `T1110`, `T1111`, `T1900` map to human-readable labels and `transaction_subject` populates `note` when `transaction_note` is absent.
- `test_reconciliation_page_in_studio_contract` in `backend/tests/test_studio_contract.py`.

---

### MR 3: `feat/sandbox-seeder-and-live-verification`

#### 3A. Idempotent Live PayPal Sandbox Seeder (`backend/scripts/seed_paypal_sandbox.py`)

- **File:** `backend/scripts/seed_paypal_sandbox.py` (new script)
- **Safety Rule:** Must require `--confirm-live` CLI flag (or `--dry-run` default) so it never mutates the live PayPal Sandbox account accidentally during automated test runs.
- **Specification:**
  1. Uses `SandboxPayPal(settings)` from `app.integrations.paypal`.
  2. **Products (`/v1/catalogs/products`):**
     - Lists existing products (`GET /v1/catalogs/products?page_size=50&total_required=true`).
     - Checks by `name` for `"Analyst Workspace"`, `"Data Add-ons"`, and `"Field Kit"`.
     - Creates any missing product via `POST /v1/catalogs/products` with deterministic `PayPal-Request-Id: pg-seed-prod-{slug}`.
  3. **Billing Plans (`/v1/billing/plans`):**
     - Lists existing plans (`GET /v1/billing/plans?page_size=50&total_required=true`).
     - Checks by `name` for `"Workspace Monthly"`, `"Workspace Annual"`, `"Add-ons Quarterly"`, and `"Field Kit Weekly Rental"`.
     - Creates any missing plan linked to the corresponding product ID via `POST /v1/billing/plans` (activating or leaving inactive to match `fixture_account()`).
  4. **Invoices (`/v2/invoicing/invoices`):**
     - Lists existing invoices (`GET /v2/invoicing/invoices?page_size=100&total_required=true`).
     - Checks by `detail.invoice_number` (`PG-1001` through `PG-1008`).
     - For each missing invoice:
       - Creates a draft invoice via `POST /v2/invoicing/invoices` with the exact recipient, line items, and currency from `fixture_account()`.
       - For non-draft statuses (`SENT`, `UNPAID`, `PAID`, `PARTIALLY_PAID`, `PARTIALLY_REFUNDED`), calls `/v2/invoicing/invoices/{id}/send` (`{"send_to_recipient": false}`) and, where applicable, records the external payment (`/v2/invoicing/invoices/{id}/payments`) or refund (`/v2/invoicing/invoices/{id}/refunds`) so the live `Revenue` and `Receivables` pages match the rich multi-status distribution of the fixture.
  5. Prints a summary table of created vs. already-present Products, Plans, and Invoices.

#### 3B. Live Verification Documentation Updates

- **Files:** `README.md`, `docs/09-implementation-framework.md`, `docs/10-execution-plan.md`, `docs/11-dashboard-ui-plan.md`
- **Specification:**
  - Update the status of the live `/api/studio/paypal` read from "mock-tested only" to **verified live against PayPal Sandbox** (`94` transactions, `2` balances, and all `3` real sandbox captures `79H28497XC211214U`, `8BR25737S32734541`, `3MT57171KG6470404` joined on `capture_id`).
  - Document `python -m scripts.seed_paypal_sandbox --confirm-live` in `README.md` under the Live Mode setup instructions.

---

### MR 4: `feat/mission-control-stages-5-to-7-and-editable-needs`

#### 4A. Interactive Post-Purchase Ops (Stages 5, 6, 7) on Settled Deal Cards

- **Files:**
  - [`backend/app/runs.py`](../backend/app/runs.py)
  - [`backend/app/api.py`](../backend/app/api.py)
  - [`frontend/src/api/client.ts`](../frontend/src/api/client.ts)
  - [`frontend/src/features/deal/DealCard.tsx`](../frontend/src/features/deal/DealCard.tsx)
- **Backend Specification (`backend/app/runs.py` & `backend/app/api.py`):**
  1. Extend `ItemState` in `backend/app/runs.py` (lines 44–84) with:
     ```python
     delivery: dict | None = None          # {"verdict": "PASS"|"LATE"|"FAIL", "problems": [...], "carrier": ..., "tracking_number": ...}
     verified_token: str | None = None     # server-side only; never serialized in public_dict()
     reconciliation: dict | None = None    # {"invoice_number": ..., "status": "CLEAN"|"FLAGGED", "flags": [...]}
     reconciled_token: str | None = None   # server-side only; never serialized in public_dict()
     payout: dict | None = None            # {"split": {...}, "batch_header": {...}}
     ```
     Include `"delivery": self.delivery`, `"reconciliation": self.reconciliation`, `"payout": self.payout`, `"has_verified_token": bool(self.verified_token)`, and `"has_reconciled_token": bool(self.reconciled_token)` in `ItemState.public_dict()` (never exposing the raw HMAC tokens).
  2. Add three step functions in `backend/app/runs.py`:
     - `step_verify_delivery(run: Run, lineage_id: str, tracking_status: str = "DELIVERED", rubric_ok: bool = True) -> dict`:
       - Requires `item.order_id` and `item.capture_id`.
       - Calls `s05_verify.verify_delivery(rt.ledger, settings.gate_secret, lineage_id, item.order_id, DeliveryReport(...))`.
       - Stores `item.delivery` and `item.verified_token = res["token"]`, emits SSE event `("5-verify", "delivery_verified", ...)`.
     - `step_reconcile_invoice(run: Run, lineage_id: str, tamper_payee: bool = False, duplicate: bool = False) -> dict`:
       - Builds a `VendorInvoice` for `item.offer.seller_id` and `Decimal(item.total)` (or spoofed payee `attacker-offshore@evil.example` if `tamper_payee=True`, or checks twice if `duplicate=True`).
       - Calls `run.forensics.check(rt.ledger, settings.gate_secret, inv)`.
       - Stores `item.reconciliation` and `item.reconciled_token = res["token"]`, emits SSE event `("6-reconcile", "invoice_checked", ...)`.
     - `step_release_payout(run: Run, lineage_id: str) -> dict`:
       - Calls `s07_payout.release_payout(rt.ledger, rt.gateway, settings.gate_secret, lineage_id, order_id=item.order_id, invoice_number=inv_no, payee_email=payee, gross=Decimal(item.total), verified_token=item.verified_token, reconciled_token=item.reconciled_token)`.
       - If either `verified_token` or `reconciled_token` is `None`, `s07_payout.release_payout` raises `GateTokenInvalid` (`GuardViolation` → HTTP `409`), proving on screen that payouts are blocked until both Stage 5 and Stage 6 pass!
       - When both tokens are present, executes the Payouts v1 call, stores `item.payout`, and emits `("7-payout", "payout_released", ...)`.
  3. Expose the 3 endpoints in `backend/app/api.py`:
     - `POST /api/runs/{run_id}/orders/{lineage_id:path}/verify`
     - `POST /api/runs/{run_id}/orders/{lineage_id:path}/reconcile` (optional query/body `{ "tamper_payee": false }`)
     - `POST /api/runs/{run_id}/orders/{lineage_id:path}/payout`
- **Frontend Specification (`DealCard.tsx`):**
  - When `item.status === 'settled'`, render a collapsible or inline **Post-Purchase Escrow & Payout (Stages 5–7)** bar on `DealCard.tsx`:
    - **Stage 5 badge & button:** `Verify delivery` → turns green (`VERIFIED token sealed`).
    - **Stage 6 badge & buttons:** `3-way match invoice` (clean) and `Simulate spoofed invoice` (flags `PAYEE_MISMATCH`, refuses token) → when clean, turns green (`RECONCILED token sealed`).
    - **Stage 7 button:** `Release supplier payout` → if clicked before Stages 5 & 6 pass, displays the 409 `GATE_TOKEN_INVALID` guard banner; once both tokens are sealed, releases the payout and shows the Gross / Fee (2% + $0.25 illustrative) / Net split and `payout_batch_id`.

#### 4B. Editable Procurement Needs in `MandateForm.tsx`

- **Files:**
  - [`frontend/src/api/client.ts`](../frontend/src/api/client.ts)
  - [`frontend/src/features/mandate/MandateForm.tsx`](../frontend/src/features/mandate/MandateForm.tsx)
  - [`frontend/src/App.tsx`](../frontend/src/App.tsx)
- **Specification:**
  1. Add `NeedInput = { category: string; description: string; quantity: number; mode: 'direct' | 'negotiate' }` to `frontend/src/api/client.ts`, initialized to the 3 default needs (`webcams` × 2 direct, `monitors` × 5 negotiate, `microphones` × 1 direct).
  2. In `MandateForm.tsx`, render a compact **"Procurement needs"** list below the mandate fields where the user can edit description, category, quantity, and mode (`Direct (Channel3)` vs `Negotiate (4 sellers)`), add a need (`+ Add need`), or remove a need, and pass `needs` alongside `mandate` to `startRun(m, needs)`.

#### 4C. Required Tests for MR 4
- `test_stage_5_to_7_endpoints_block_payout_until_both_tokens_sealed` in `backend/tests/test_runs.py`:
  - Settle an item via the step functions.
  - Call `POST /api/runs/{id}/orders/{lid}/payout` before Stage 5/6 → assert HTTP `409` with `code == "GATE_TOKEN_INVALID"`.
  - Call `/verify` → assert `verdict == "PASS"`.
  - Call `/payout` before Stage 6 → assert HTTP `409` (`RECONCILED` still missing).
  - Call `/reconcile` with `tamper_payee=True` → assert `status == "FLAGGED"` and `/payout` still returns `409`.
  - Call `/reconcile` with clean invoice → assert `status == "CLEAN"`.
  - Call `/payout` → assert HTTP `200` and `batch_header.payout_batch_id` is returned.

---

### MR 5: `feat/escalate-only-injection-classifier-and-deploy`

#### 5A. Escalate-Only LLM Prompt-Injection Guard in `s03_govern.py`

- **Files:**
  - [`backend/app/stages/s03_govern.py`](../backend/app/stages/s03_govern.py)
  - [`backend/app/integrations/llm.py`](../backend/app/integrations/llm.py)
  - [`backend/eval/firewall_cases.py`](../backend/eval/firewall_cases.py)
  - [`backend/eval/RESULTS.md`](../backend/eval/RESULTS.md)
- **Specification:**
  1. Preserve the core invariant (**Rule 1: Money decisions are deterministic; the LLM can never approve or loosen a constraint**):
     - In `s03_govern.py`, keep `scan_injection(texts)` as the fast, deterministic regex tripwire (`< 0.1 ms`).
     - Add an optional `llm_injection_check(llm: LLM | None, texts: list[str]) -> list[str]` that is called **only** when:
       1. `scan_injection(texts)` returned `[]` (no regex match),
       2. `llm is not None` and `llm.enabled`, and
       3. `texts` is non-empty.
     - Use `llm.structured` with a strict schema `{"injected": bool, "reason": str}` asking whether the untrusted seller/item text attempts to override instructions, alter payment routing, or claim pre-authorization.
     - **One-way ratchet:** If `injected is True`, append `"llm-classifier: " + reason` to `warrant_problems` (forcing `route = "BLOCKED"`). If `injected is False` or the LLM call errors/times out, do nothing—all four deterministic numeric factors (`warrant`, `reversibility`, `price`, `budget`) still govern the transaction unchanged.
  2. Re-run `PYTHONPATH=backend backend/.venv/bin/python -m eval.run_all` and update `backend/eval/RESULTS.md`.

#### 5B. Render Deployment & Submission Checklist Verification

- **Files:** `render.yaml`, `README.md`
- **Specification:**
  1. Confirm `render.yaml` sets `REPLAY_MODE=true` by default for public safety, generates a random `GATE_SECRET` (`generateValue: true`), runs with `--workers 1`, and serves `FRONTEND_DIST=../frontend/dist`.
  2. Document the live webhook registration (`POST /api/webhooks/paypal`) and final check commands in `README.md`.

---

## 4. Verification Protocol for Every MR

Every agent executing an MR from this plan **must** run the following four checks before opening or merging its PR:

```bash
# 1. Backend test suite (must pass 100%, growing from 155 to ~165+ tests across MRs 1–5)
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests -q

# 2. Backend linter & formatter check (0 errors, 0 unformatted files)
backend/.venv/bin/ruff check backend
backend/.venv/bin/ruff format --check backend

# 3. Frontend linter (0 warnings, 0 errors)
npm --prefix frontend run lint

# 4. Frontend TypeScript & production bundle build
npm --prefix frontend run build
```
