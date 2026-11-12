# Disputes, returns and shipment tracking

Stage 8 ("Defend") and its link to stage 5 ("Verify"). A buyer can dispute a purchase in PayPal's Resolution Center; PactGuard reads that case, assesses it from records it sealed **before** the dispute existed, recommends a response with the reasoning shown, and a person decides what is sent. The same desk handles refunds, partial refunds, return-for-refund and the shipment data that backs them.

Code: `backend/app/stages/s08_defend.py` (assessment and responses), `s05_verify.py` (delivery proof), `s10_learn.py` (what outcomes teach), `backend/app/api.py` (endpoints), `frontend/src/features/dispute/DisputeDesk.tsx` (the desk). Tests: `test_disputes.py`, `test_dispute_playbooks.py`, `test_dispute_returns.py`, `test_live_dispute_probe.py`.

## What you can do from the UI

The **Dispute desk** (section 8 of Mission Control) lists every open PayPal dispute, soonest deadline first, each with its reason, win odds and recommendation. Open a case and you get:

1. **The facts**, read from the sealed ledger: when the order was sealed, the return window that was agreed, whether a person approved the purchase, the delivery proof, the amounts sealed and captured, other captures that could be duplicates, earlier disputes, and whether the ledger chain still verifies.
2. **Options with expected value**, each marked available or excluded, with the rule that excluded it.
3. **A recommendation**, only when PayPal is actually waiting on you and a playbook applies.
4. **An editable draft reply**, built only from sealed facts. "Polish wording" optionally rewords it with Claude (tone only; the facts are passed in and nothing new may be added).
5. **The evidence brief** as a PDF download, and a **case timeline** in your local time zone: purchase sealed, dispute opened, messages, return tracking, inspection, your responses with the approver, and the outcome.
6. **Send to PayPal**, behind a confirmation. Nothing reaches PayPal without that click.

Beside the case you can also **record shipment tracking** and **record a return inspection** (below).

## Where cases come from

- **Live sandbox:** the buyer opens a dispute in the sandbox Resolution Center. The desk polls `/api/disputes` every 10 seconds while the tab is visible (one PayPal call per open case per poll). The lineage ID PayPal echoes back in `disputed_transactions[].custom` finds the sealed record; if it is missing, the seller transaction ID is matched against ledger `capture` entries. A case with no sealed record is shown, but contesting it is refused.
- **Replay:** the desk can simulate a buyer dispute on any settled purchase (six reasons: stopped working, never arrived, charged twice, wrong amount, unauthorised, refund not received), simulate the buyer shipping a return, and simulate PayPal's decision (we win, buyer wins). It is the same code path with a deterministic stand-in for PayPal.

## How a case is assessed

`s08_defend.assess` is deterministic: facts from the ledger, the playbook for the dispute's reason, an expected value per option, hard rules, and only the channels PayPal currently allows (its HATEOAS `links` decide what is possible). An LLM never decides.

**Win odds** start from how much of the required evidence exists (seal, decision, approval, delivery proof, capture, depending on the reason), plus credit for a passed delivery proof and an intact chain, and are capped by the situation: no more than 15% for "not received" without carrier proof, no more than 35% when the buyer describes a defect (a checkout seal proves what was sold, not that this unit still works), and at least 85% when the carrier confirms delivery.

**Expected value** (estimates, labelled as such at the top of `s08_defend.py`):

| Option | Value |
|---|---|
| Contest | odds × disputed amount − handling cost ($15 at inquiry, $20 chargeback, $25 pre-arbitration or arbitration) |
| Refund on return | recovery × amount − $8 return label (item worth about 30% back for a defect, 80% otherwise) |
| Share tracking and wait | 80% × amount, for a parcel in transit and not yet late |
| Refund the overcharge | the amount kept after refunding only the difference |
| Confirm return and refund | recovery × amount; or 50% × amount if the parcel arrived with a problem |
| Accept and refund | $0.00 (the baseline surrender) |

### Playbooks by dispute reason

| Reason | Ledger check | Recommends |
|---|---|---|
| Item not received | Carrier tracking in a `delivery_proof` | **Contest** with proof of fulfilment if delivered. **Share tracking and wait** if in transit and not late (refunding is then blocked). Otherwise **refund**. Never refund-with-return: PayPal rejects it on goods never delivered. |
| Not as described | Sealed return window, buyer's note | Never contest inside our own return window. A defect claim caps odds at 35%, so **refund on return** usually wins. |
| Duplicate charge | Another capture, same vendor and amount, within 48 hours, anywhere in the mandate | Found: **refund** (contest blocked). One capture only: **contest**, since the deterministic request ID proves one order. |
| Incorrect amount | Captured against sealed amount | Captured more: **refund the overcharge** only. Equal: **contest** from the penny-exact seal. |
| Refund not processed | Any earlier refund commitment | Committed: honour it (contest blocked). |
| Unauthorised | Delivery proof and human approval | Flagged for security review; contest only with both. |
| Recurring billing, paid by other means | Captures on the purchase | One capture: **contest**. More: no contest. |
| Anything else | | No automatic recommendation: manual review. |

### Hard rules

Never contest without a sealed record. Never contest a not-as-described claim inside our own return window. Never offer refund-with-return on goods never delivered. Nothing once the seller response window has closed. Refund-with-return needs a configured returns address. Only the case state `WAITING_FOR_SELLER_RESPONSE` gets a recommendation; waiting on the buyer, under PayPal review and resolved cases are shown as such. Flags are raised for a purchase disputed before, a disputed amount above the captured amount, a duplicate capture and a possibly compromised buyer account.

## What the desk can send

Each response is sent once per case, only if PayPal lists the action as allowed right now, and only on a person's click. The ledger records the option, channel, expected value, whether the recommendation was followed, the approver and a hash of the note (not the text).

| Desk option | PayPal call |
|---|---|
| Contest with sealed evidence | `provide-evidence`: structured evidence plus the PDF brief, as proof of fulfilment when delivery is proven |
| Share tracking and wait; any reply when only messaging is allowed | `send-message` |
| Refund on return | `make-offer` with `REFUND_WITH_RETURN` and the returns address |
| Refund the overcharge, partial refund | `make-offer` with a money-only `REFUND` below the disputed amount |
| Accept and refund | `accept-claim` |
| Confirm return received and refund | `acknowledge-return-item` |

## Returns

For a refund on return the full cycle runs through the desk:

1. The operator sends `REFUND_WITH_RETURN`, with the returns address from `RETURN_ADDRESS_*` (required in live mode).
2. If the buyer accepts, PayPal lists `acknowledge_return_item` and the buyer's return tracking appears in the case (`PROOF_OF_RETURN`). The desk shows the carrier and number and recommends nothing while the parcel is on its way.
3. **A person inspects the parcel and records what arrived** (`POST /api/disputes/{id}/return-received`): item received, damaged, missing items, empty box or different item, or never arrived. That condition is sealed in the ledger first, because `ITEM_RECEIVED` makes PayPal refund at once and buyer-uploaded tracking proves nothing about the contents.
4. The acknowledgement then goes out with that condition. Only `ITEM_RECEIVED` releases the refund; the other conditions hand the case to PayPal review with the inspection on record.

## Shipment tracking (stage 5)

Carrier tracking becomes **sealed delivery proof** that the dispute evidence can cite.

- **Record tracking** in the desk (carrier, tracking number, status `DELIVERED`, `IN_TRANSIT` or `LOST`, delivery date, due date), or `POST /api/deliveries` for any sealed purchase, live or replay. The desk offers it on a case whose delivery is not yet proven.
- `verify_delivery` checks the report against the sealed terms and returns **PASS**, **LATE** or **FAIL** (wrong status, delivered after the due date, or a failed acceptance rubric) and seals a `delivery_proof` entry. Only PASS mints the `VERIFIED` gate token that a payout needs; the token never leaves the server.
- That proof is what turns a "not received" dispute from losing to winnable: with carrier-confirmed delivery the desk attaches proof of fulfilment and win odds rise from about 15% to 85% or more; without it, contesting is rationally avoided.
- It also feeds stage 10: delivery verdicts count towards each supplier's trust score.

The tracking data is **entered by the operator**, not fetched from a carrier. In the demo, Mission Control's post-purchase button uses a scripted carrier report.

## What outcomes teach (stage 10)

When PayPal resolves a case, its outcome code is recorded once as **WON**, **LOST** (we contested and lost) or **SETTLED** (we chose to refund). Supplier trust is a Beta(2, 1) estimate: a new supplier starts at 67% and each delivery PASS or WON raises it, each failed or late delivery, LOST or SETTLED lowers it. A supplier under 50% is removed from the allowlist, and any lost contest cuts the auto-approve threshold by 25%. A SETTLED refund lowers trust (a defect return is a quality signal) but does not tighten the mandate, because the agent did not lose a fight. The new mandate is a new version linked to the old one, shown as a before and after diff in the Command Center.

## Ledger entries written

`delivery_proof` (stage 5), `dispute_response` (option, channel, amount, odds, expected value, approver, note hash), `return_received` (condition, inspector, note), `dispute_outcome` (WON, LOST or SETTLED, supplier). The ledger is append-only, so a mistaken label is explained, not edited.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/disputes` | Open cases with recommendation, odds, days left, flags |
| `GET /api/disputes/{id}` | Case, assessment, drafts per option, timeline |
| `GET /api/disputes/{id}/brief.pdf` | The evidence brief |
| `POST /api/disputes/{id}/draft` | Draft reply, optionally reworded by Claude |
| `POST /api/disputes/{id}/respond` | Send the chosen response (human approval) |
| `POST /api/disputes/{id}/return-received` | Seal the return inspection |
| `POST /api/deliveries` | Seal carrier tracking as delivery proof |
| `POST /api/runs/{run}/disputes/simulate`, `/api/disputes/{id}/simulate-return`, `/simulate-resolve` | Replay only |

## Safety properties

- A person sends every response; the agent only recommends.
- Evidence comes from records sealed before the dispute, and the ledger chain is verified before it is cited.
- Only actions PayPal currently allows are offered, and each is sent once.
- The LLM can reword a draft but cannot add facts, and the recommendation never depends on it.
- The refund is never released on the buyer's word: it needs a recorded inspection.

## What has been verified against the real sandbox

- **A dispute taken from open to closed live, through the desk** (case `PP-R-PSL-10196709`, 2026-11-06): the buyer opened a not-as-described case, the desk matched the sealed order, found the return window open and recommended refund on return; the operator sent `make-offer` with `REFUND_WITH_RETURN`; the buyer accepted and uploaded return tracking; the operator sent `acknowledge-return-item`; PayPal resolved the case with the refund, and the outcome synced into the ledger.
- `accept-claim` was accepted by PayPal and resolved a live case. A money-only partial `REFUND` offer built by the production code was accepted by PayPal on a live item-not-received case (sent with `scripts/live_dispute_probe.py`, which is a test of PayPal's API, not an agent decision, and writes nothing to the ledger).
- Two PayPal rejections found live and fixed: `INVALID_OFFER_TYPE` (refund-with-return on goods never delivered) and `MISSING_RETURN_SHIPPING_ADDRESS`.
- **Not yet verified live:** the multipart `provide-evidence` upload (only the replay gateway has received it), and the desk's own `partial_refund` recommendation sent end to end. In that live case the acknowledgement was sent on the buyer's tracking alone, which is why the inspection step now exists; the case's ledger entry still reads LOST from before the SETTLED label was added.

## Configuration

`RETURN_ADDRESS_LINE_1`, `RETURN_ADDRESS_CITY`, `RETURN_ADDRESS_STATE`, `RETURN_ADDRESS_POSTAL_CODE`, `RETURN_ADDRESS_COUNTRY`: where a buyer ships a returned item. PayPal shows it to the buyer, so use a real returns address in live mode; live mode refuses a refund-with-return offer if it is unset, and replay uses a labelled demo address. `ANTHROPIC_API_KEY` is optional and only rewords drafts. The cost constants (handling cost, return label, recovery rates) are estimates in `s08_defend.py`: tune them.
