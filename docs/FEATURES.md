# Feature guide

Everything PactGuard AI does, by area, with where it lives and what it guarantees. The [README](../README.md) is the short version and says what is live versus simulated; [ARCHITECTURE.md](ARCHITECTURE.md) explains the shared primitives and guard table; [DISPUTES.md](DISPUTES.md) covers disputes, returns and shipment tracking in depth; [OPERATIONS.md](OPERATIONS.md) covers running it.

## Mission Control (the buyer's view)

- **Mandate form.** Budget, auto-approve threshold, per-transaction cap, minimum return days, vendor allowlist, allowed categories and an approval mode (*auto plus review gate*, or *review everything*). Two presets (Office setup, $2.2k; Strict review, $1.2k). Inputs are validated: the auto threshold cannot exceed the cap or the budget, lists cannot be empty, return days must be whole.
- **What to buy.** The shopping list is yours: description, quantity (1 to 25), category and buy method (direct, or negotiate with sellers) per item, up to six items. A category outside the allowed list shows a warning that the firewall will block it.
- **Run agent.** Discovery, negotiation, firewall and settlement stream into the page as server-sent events. A six-stage rail tracks progress; the hero shows budget, auto threshold, captured count and blocked-or-held count.
- **Needs your decision.** Purchases held for a person appear first, with the vendor, price and the firewall's reason, and one-click Approve or Reject. Each deal card shows the four firewall factors, the order and capture IDs, and the sealed order.
- **Market discovery.** One horizontally scrolling row per item type: product image, title, merchant, price against the median, return terms, and whether the vendor is on the allowlist. Beside it, a **Timeline** streams every event of the run.
- **Post-purchase checks.** One button per settled purchase runs stages 5 to 7 (see below).
- **Run 10-Stage Showcase.** One header button runs the entire loop in about a second on a fresh in-memory ledger and summarises it.
- **Replay or live badge.** Click it for an explanation of replay mode, why it is the default, and how to use the real sandbox.
- **Run in PayPal sandbox.** Where the server allows it, one confirmed run uses the real sandbox (see OPERATIONS).

## Mandate and firewall (stages 1 and 3)

- A mandate is hashed into the **root of a lineage ID**, and every later call and ledger row carries it. Mandates are versioned and linked by their parent's digest.
- The **four-factor firewall** (`s03_govern`) runs in front of every money movement, orders and payouts alike, in well under a millisecond with no LLM in the path:
  - **Warrant** (hard): not an injection, vendor on the allowlist, category allowed, and a payout is never issued by an agent tool call.
  - **Reversibility** (soft): return terms known and at least the mandate's minimum. Hidden terms route to a human.
  - **Price** (soft): within the mandate's maximum premium over the discovery baseline.
  - **Budget** (hard): the total fits the budget (captured spend plus sealed-but-uncaptured orders) and the per-transaction cap.
  A hard failure blocks. A soft failure, a total over the auto threshold, or review-first mode routes to a human. Otherwise it auto-settles. The decision, its factors and a digest are sealed in the ledger.
- **Prompt-injection tripwire.** About a dozen patterns scan untrusted text (seller messages). Untrusted text can only ever block a route, never approve one. The weak spot is stated in the README: it caught 1 of 5 held-out paraphrases.
- **Simulate prompt-injection attack** injects a $900 payout proposal hidden in seller text and shows it blocked, with the reasons and latency.
- **Human approval** mints a signed `APPROVED` token bound to one decision; settlement refuses without it.

## Discovery and negotiation (stage 2)

- Live product search on **Channel3** gives a retail baseline and candidate sellers. Channel3 does not return return policies, so a labelled retailer table supplies them.
- **Negotiation** is a buyer against four simulated sellers over exactly three bounded turns (quote, counter, final). Every seller message must pass a strict schema gate (`extra="forbid"`) or that seller is dropped (one of the four sends malformed offers on purpose). A reservation book allows exactly one commitment; the runners-up are cancelled. The negotiation table shows each seller's offers by turn, the buyer's counters, and the winner.

## Settlement and idempotency (stage 4)

- **Seal before money.** The agreed terms (price, quantity, return and shipping terms, a hash of the terms text, buyer IP, how the buyer paid) are sealed before PayPal is called, and capture refuses without that seal. A saved-wallet order is sealed first because the order is captured on creation.
- **Penny-exact money** (`Decimal` throughout) makes `AMOUNT_MISMATCH` unreachable, and only `captures[].status == COMPLETED` counts as captured.
- **Deterministic request IDs** derive from the lineage, so a retry returns the original order. The **Retry create-order** button on a deal proves it: same order ID, no double charge.
- **PayPal order and seal** can be opened on any deal. **Saved-wallet capture** pays with no popup; orders that need a person use the PayPal JS SDK button.
- **Budget accounting** counts sealed-but-uncaptured orders (they expire after 30 minutes) and capture re-checks it, so a lapsed hold can never be captured over budget.

## Verify, reconcile and pay out (stages 5 to 7)

- **Delivery proof** (stage 5): tracking checked against the sealed terms (status, due date, acceptance rubric), verdict PASS, LATE or FAIL, sealed in the ledger. Only PASS mints the `VERIFIED` token. Shipment details are covered in [DISPUTES.md](DISPUTES.md).
- **Invoice forensics** (stage 6), before any payout: a three-way match of vendor invoice against the sealed order and the delivery proof; a payee check against the vendor's registered payee; and **duplicate detection** that blends BM25 text scoring with character-trigram cosine similarity (a dependency-free stand-in for embeddings, chosen so that `INV-1001` and `INV-1010` do not collapse together). Flags are `NO_PO`, `AMOUNT_MISMATCH`, `NO_DELIVERY_PROOF`, `UNKNOWN_VENDOR`, `PAYEE_MISMATCH` and `DUPLICATE`. Only a clean invoice mints the `RECONCILED` token. In the post-purchase sequence, a spoofed resubmission (same invoice, different payee) is flagged.
- **Payout** (stage 7) needs **both** tokens. It computes the supplier's gross-to-net split (2% plus $0.25 fee, illustrative), derives `sender_batch_id` from the lineage (PayPal rejects a reused one, a second layer of idempotency), and records the payout. In the demo it is first attempted without a token and refused, then released.

## Webhooks (stage 7)

- A **webhook inbox** verifies each delivery, de-duplicates by event ID, and stores it in the ledger so a redelivery after a restart is still caught. The **Webhook inspector** lists accepted events, can simulate a delivery, and re-deliver the latest one. In live mode verification is PayPal's `verify-webhook-signature` against the exact bytes received; in replay a replay signature is accepted. Not yet checked against a real PayPal event.

## Disputes, returns and shipment tracking (stage 8)

See [DISPUTES.md](DISPUTES.md): PayPal disputes read from the sandbox Resolution Center, assessed by reason with expected value, answered by a person (contest with a PDF evidence brief, share tracking, refund, partial refund, refund on return, accept), the return and inspection lifecycle, and sealed shipment tracking.

## Learning (stage 10)

- **Supplier trust** is a Beta(2, 1) score per vendor: a new supplier starts at 67%, and delivery PASS and WON raise it while failed or late deliveries, LOST and SETTLED lower it. A supplier under 50% is dropped from the allowlist; a lost contest cuts the auto threshold by 25%; five approvals with no rejections raises it by 10%. The result is a new mandate version, shown as a **before and after diff**. `GET /api/runs/{id}/calibration` previews it without writing.

## Evidence ledger

- Append-only (database triggers), hash-chained, each head signed with `GATE_SECRET`. The **Evidence ledger** panel verifies the chain live. Clicking a purchase row opens its **sealed lineage** drawer: every entry for that purchase, in order, with hashes. `GET /api/ledger/checkpoint` returns a signed head anchor to keep off the machine; `GET /api/ledger/verify` accepts one to detect truncation.
- **Seeded history:** about thirty synthetic mandates run through the same step functions as a live run (only the inputs are synthetic), with timestamps spread over past days inside the hash chain, so the history verifies like any other ledger (`GET /api/studio/history/verify`).

## Command Center (AG Studio)

- Seven pages in two groups. **Agent:** Purchases (spend, savings, firewall routes, dispute outcomes, supplier trust, a transactions grid), Agent Activity (decisions by day, firewall latency, escalations) and **Reconciliation** (each captured agent purchase against PayPal's ledger by capture ID, with a status of Matched, Amount mismatch, Pending, Outside window, Unsettled, Simulated, Sandbox capture or Not decided by agent). **PayPal account:** Revenue, Receivables, Cash and Catalogue, read from the merchant's account (invoices, payments, products, billing plans, 31 days of Transaction Search, payouts, balances) and joined to agent captures.
- Click a purchase row for its sealed lineage, or a capture ID for the PayPal transaction; a mandate v1 to v2 diff sits beside it.
- **Live feed:** new and changed purchases are applied to Studio as data transactions, with pause and a 2, 5 or 10 second interval. Edit mode opens Studio's composer for building your own widgets.
- **AI assistant.** Claude (Haiku 5.5) behind AG Studio's AI harness through an adapter we wrote for its `AgLlmAdapter` contract, with the key held server-side behind a rate-limited proxy. It knows the data model and has starter prompts: summarise a page, where the firewall stepped in, agent captures in PayPal, agent versus PayPal, lost disputes, overdue invoices, and add a chart. It runs inside Studio's own AI harness.

## Replay mode and testing

- **Replay gateways** for PayPal, Channel3 and the LLM honour request-ID idempotency and can inject the failures the guards defend against, so the whole product runs offline and deterministically.
- **Tests:** 194 backend tests, one per row of the hand-off guard table plus API, disputes, webhooks, reconciliation, sandbox runs, ledger and contract tests. **Evaluation harness** (`backend/eval`): 55 firewall scenarios, 20 negotiation runs with injected misbehaving sellers, and idempotency retries of each money operation, reported with their weak spot.
- **CI** runs ruff, pytest, oxlint and the frontend build on every push; a keep-warm workflow pings the deployed service.
- An **APIMatic** check validates the Orders v2 payloads against the generated PayPal SDK models (`backend/scripts/apimatic_check.py`).

## Implemented but not wired into the app

Be careful not to claim these in the demo. **Invoicing v2** (draft-first invoice issue and overdue reminders, one per invoice per day) is implemented in the stage code and covered by the idempotency tests, but no screen or endpoint triggers it. The Command Center's Revenue, Receivables and Catalogue pages read the merchant account's invoices, products and plans, which the sandbox account used here does not have, so they are empty in a live read (the replay fixture fills them). **Payouts v1** has been run against the sandbox once, but the demo's payout is scripted and is skipped in a live or sandbox run.
