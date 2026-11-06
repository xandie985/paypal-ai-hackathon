// The Command Center's AI assistant: Claude behind AG Studio's AI harness. The adapter posts to this
// app's own proxy (backend/app/ai_proxy.py), which holds the Anthropic key, so nothing secret is sent
// from the browser.

import { createAiHarness, type AgAiHarnessSetup, type AgAiPromptStarter } from 'ag-studio'
import { claudeAdapter } from './claudeAdapter'

// What the model needs to know about the data it can query. Field ids and names come from the report's
// data source in CommandCenter.tsx.
const DOMAIN = `You are the analyst inside PactGuard AI's Command Center, an AG Studio report over the hash-chained evidence ledger of an autonomous purchasing agent.
- The "Transactions" table has one row per purchase lineage (a PG-… id shared by every ledger entry of that purchase).
- "route" is the mandate firewall's decision: AUTO_SETTLE (within the auto-approve threshold), HUMAN_APPROVAL (a person must approve) or BLOCKED (a rule failed; see "blocked_reasons").
- "status" is CAPTURED once PayPal captured the payment, or REJECTED if a human declined it. Only captured purchases are real spend.
- "savings" is measured against the retail baseline. "supplier_trust" is the per-vendor score (0-100%) learned from delivery proof and dispute outcomes. "dispute_outcome" is WON, LOST or SETTLED.
- All money is USD. Prefer the existing fields over inventing new ones, and say plainly when the data cannot answer a question.`

const PROMPT_STARTERS: AgAiPromptStarter[] = [
  {
    label: 'Summarise this page',
    prompt: 'Summarise what this page shows: every widget, the fields it reads, and what stands out.',
  },
  {
    label: 'Where the firewall stepped in',
    prompt: 'How many purchases did the firewall block or send to a human, and what were the most common reasons?',
  },
  {
    label: 'Lost disputes',
    prompt: 'Which purchases ended in a LOST or SETTLED dispute, and which suppliers were they from?',
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
