// The Command Center's AI assistant: Claude behind AG Studio's AI harness. The adapter posts to this
// app's own proxy (backend/app/ai_proxy.py), which holds the Anthropic key, so nothing secret is sent
// from the browser.

import { createAiHarness, type AgAiHarnessSetup, type AgAiPromptStarter } from 'ag-studio'
import { claudeAdapter } from './claudeAdapter'

// What the model needs to know about the data it can query. Field ids and names come from the report's
// data source in CommandCenter.tsx.
const DOMAIN = `You are the analyst inside PactGuard AI's Command Center, an AG Studio report over the hash-chained evidence ledger of an autonomous purchasing agent.
- The "Transactions" table has one row per purchase lineage (a PG-… id shared by every ledger entry of that purchase). It powers the "Purchases" and "Agent Activity" pages.
- "route" is the mandate firewall's decision: AUTO_SETTLE (within the auto-approve threshold), HUMAN_APPROVAL (escalated to a person) or BLOCKED (a rule failed; see "blocked_reasons"). "firewall_ms" is the deterministic firewall latency in milliseconds, and "approved_by" records who approved or rejected an escalated purchase.
- "status" is CAPTURED once PayPal captured the payment, or REJECTED if a human declined it. Only captured purchases are real spend.
- "savings" is measured against the retail baseline. "supplier_trust" is the per-vendor score (0-100%) learned from delivery proof and dispute outcomes. "dispute_outcome" is WON, LOST or SETTLED, and "dispute_win_odds" is the desk's estimated win probability.
- The other tables are the merchant's own PayPal sandbox account (they can be absent if the sandbox read failed): "PayPal Customers" (invoice recipients), "PayPal Invoices" (status, due date, paid, outstanding, overdue and aging), "Invoice Line Items", "Invoice Payments" (payments and refunds; "Net Cash" is signed), "PayPal Products", "Billing Plans" (monthly-normalised price, trial days), "PayPal Transactions" (the account ledger from Transaction Search, last 31 days, signed amounts), "PayPal Payouts" (positive amounts, grouped into campaigns) and "PayPal Balances".
- "Transactions.capture_id" is related many-to-one to "PayPal Transactions.id", linking an agent purchase decision to the PayPal capture that moved the money. Invoices are related to customers, and line items and payments to invoices; plans to products. Their pages are Revenue, Receivables, Cash and Catalogue. Invoices are USD or EUR and not converted, so filter by currency before summing them.
- Purchase amounts are USD. Prefer the existing fields over inventing new ones, and say plainly when the data cannot answer a question.`

const PROMPT_STARTERS: AgAiPromptStarter[] = [
  {
    label: 'Summarise this page',
    prompt: 'Summarise what this page shows: every widget, the fields it reads, and what stands out.',
  },
  {
    label: 'Where the firewall stepped in',
    prompt: 'How many purchases did the firewall block or escalate to a human, what was the average firewall latency, and what were the most common block reasons?',
  },
  {
    label: 'Agent captures in PayPal',
    prompt: 'Which captured agent purchases in Transactions match a row in PayPal Transactions by capture_id, and what were their PayPal fees and net amounts?',
  },
  {
    label: 'Lost disputes',
    prompt: 'Which purchases ended in a LOST or SETTLED dispute, and which suppliers were they from?',
  },
  {
    label: 'Overdue invoices',
    prompt: 'Which PayPal invoices are overdue, how much is outstanding per currency, and which customers owe it?',
  },
  {
    label: 'Savings by category',
    prompt: 'Add a chart of captured savings by category.',
  },
]

export function buildAi(model: string): AgAiHarnessSetup {
  const adapter = claudeAdapter({ endpoint: '/api/ai', model, system: DOMAIN })
  return ({ api }) => createAiHarness(api, { adapter, promptStarters: PROMPT_STARTERS })
}
