export type Factor = { name: string; passed: boolean; hard: boolean; detail: string }
export type Decision = {
  lineage_id: string
  route: 'AUTO_SETTLE' | 'HUMAN_APPROVAL' | 'BLOCKED'
  factors: Factor[]
  reasons: string[]
  latency_ms: number
}
export type OfferT = {
  seller_id: string
  sku: string
  turn: number
  action: string
  unit_price: string
  quantity: number
  return_days: number
  ship_days: number
  terms: string
}
export type Seal = {
  order_id: string
  amount: string
  currency: string
  seller_id: string
  sku: string
  unit_price: string
  quantity: number
  return_days: number
  ship_days: number
  terms_hash: string
  terms_text: string
  decision_digest: string
  buyer_ip: string
}
export type PurchaseUnit = {
  reference_id: string
  custom_id: string
  amount: { currency_code: string; value: string; breakdown?: Record<string, { value: string }> }
  items?: { name: string; sku: string; quantity: string; unit_amount: { value: string } }[]
}
export type Item = {
  lineage_id: string
  title: string
  method: 'direct' | 'negotiate'
  status: string
  decision: Decision | null
  order_id: string | null
  capture_id: string | null
  offer: OfferT
  baseline: string | null
  return_days: number | null
  total: string
  saving: string | null
  seal: Seal | null
  purchase_unit: PurchaseUnit | null
  order_status: string | null
}
export type RunSnapshot = {
  run_id: string
  mandate_lineage: string
  complete: boolean
  items: Item[]
  budget: string
  spent: string
  ledger_entries: number
}
export type Candidate = {
  product_id: string
  title: string
  merchant: string
  category: string
  price: string
  return_days: number | null
  url: string
  image_url: string
  source: string
  allowlisted: boolean
}
export type TranscriptRow = {
  turn: number
  from?: 'seller' | 'buyer'
  seller_id?: string
  event?: string
  action?: string
  unit_price?: string
  return_days?: number
  ship_days?: number
  terms?: string
}
export type LedgerEntry = {
  seq: number
  lineage_id: string
  stage: string
  kind: string
  payload_hash: string
  prev_hash: string
  entry_hash: string
  created_at: string
}
export type LedgerView = { chain_ok: boolean; first_bad_seq: number | null; entries: LedgerEntry[] }
// One row per purchase lineage from GET /api/studio/rows. Money arrives as decimal strings.
export type StudioRow = {
  lineage_id: string
  source: 'run' | 'demo' | 'seeded' // seeded = synthetic history run through the real step functions
  created_at: string // ISO-8601 UTC from the ledger
  updated_at: string
  order_id?: string
  capture_id?: string
  vendor?: string
  category?: string
  action?: string
  route?: Decision['route']
  amount?: string
  savings?: string
  firewall_ms?: number
  blocked_reasons?: string
  approved_by?: string
  status?: string
  delivery?: string
  invoice_status?: string
  payout_net?: string
  dispute_win_odds?: number
  dispute_outcome?: string
  supplier_trust?: number
}
export type RunEvent = { seq: number; stage: string; event: string; [k: string]: unknown }
export type MandateInput = {
  principal: string
  purpose: string
  budget: string
  auto_threshold: string
  per_txn_cap: string
  vendor_allowlist: string[]
  allowed_categories: string[]
  min_return_days: number
  mode: 'auto' | 'review_first'
}

export type DisputeCase = {
  dispute_id: string
  reason: string
  stage: string
  status: string
  amount: string
  currency: string
  lineage_id: string | null
  capture_id: string | null
  item_name: string
  buyer_note: string
  due_date: string | null
  created: string | null
  updated: string | null
  actions: string[]
  messages: { posted_by: string; time_posted: string | null; content: string }[]
  outcome: string | null
}
export type DisputeOption = {
  option: 'contest' | 'inform' | 'partial_refund' | 'refund_with_return' | 'acknowledge_return' | 'accept'
  via: string
  amount?: string
  ev: string
  basis: string
  available: boolean
  excluded_by: string | null
}
export type DisputeAssessment = {
  dispute_id: string
  lineage_id: string | null
  win_odds: number
  days_left: number | null
  recommended: DisputeOption['option'] | null
  reason_label: string
  playbook: string | null
  state_note: string | null
  flags: string[]
  options: DisputeOption[]
  facts: Record<string, unknown> & { lineage_found: boolean; claim: string }
}
export type DisputeSummary = {
  case: DisputeCase
  recommended: string | null
  win_odds: number
  days_left: number | null
  lineage_found: boolean
  reason_label: string
  state_note: string | null
  flags: string[]
}
export type DisputeEvent = { at: string; who: string; what: string }
export type DisputeDetail = { case: DisputeCase; assessment: DisputeAssessment; drafts: Record<string, string>; timeline: DisputeEvent[] }
export type DeliveryInput = {
  lineage_id: string
  carrier: string
  tracking_number: string
  tracking_status: 'DELIVERED' | 'IN_TRANSIT' | 'LOST' | 'NONE'
  delivered_on?: string
  due_by: string
}

// Guards come back as 409 with {guard, message}; surface the guard's name to the UI.
export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'object' && detail ? JSON.stringify(detail) : String(detail))
    this.status = status
    this.detail = detail
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new ApiError(r.status, data.detail ?? data)
  return data as T
}

const base = (id: string) => `/runs/${id}`

export const api = {
  health: () => call<{ replay_mode: boolean; paypal_live: boolean; paypal_client_id?: string | null; currency?: string }>('GET', '/health'),
  startRun: (mandate?: MandateInput) => call<RunSnapshot>('POST', '/runs', mandate ? { mandate } : {}),
  getRun: (id: string) => call<RunSnapshot>('GET', base(id)),
  approve: (id: string, lid: string) => call<RunSnapshot>('POST', `${base(id)}/decisions/${lid}/approve`, {}),
  reject: (id: string, lid: string) => call<RunSnapshot>('POST', `${base(id)}/decisions/${lid}/reject`, {}),
  prepare: (id: string, lid: string) => call<{ order_id: string }>('POST', `${base(id)}/orders/${lid}/prepare`),
  capture: (id: string, lid: string) => call<{ capture_id: string }>('POST', `${base(id)}/orders/${lid}/capture`),
  retry: (id: string, lid: string) => call<{ order_id: string; same_order: boolean }>('POST', `${base(id)}/orders/${lid}/retry`),
  attack: (id: string) => call<{ route: string; reasons: string[]; latency_ms: number }>('POST', `${base(id)}/attack`),
  ledger: (id: string) => call<LedgerView>('GET', `${base(id)}/ledger`),
  events: (id: string) => new EventSource(`/api${base(id)}/events`),
  studioRows: (runId?: string, history = false) => {
    const q = new URLSearchParams()
    if (runId) q.set('run_id', runId)
    if (history) q.set('history', 'true')
    return call<{ rows: StudioRow[]; kpis: Record<string, string | number> }>('GET', `/studio/rows${q.size ? `?${q}` : ''}`)
  },
  studioLineage: (lineage: string) => call<LineageView>('GET', `/studio/lineage/${encodeURIComponent(lineage)}`),
  studioCalibrations: () => call<{ calibrations: Calibration[] }>('GET', '/studio/calibrations'),
  runCalibration: (runId: string) => call<RunCalibration>('GET', `/runs/${runId}/calibration`),
  aiConfig: () => call<{ configured: boolean; model: string }>('GET', '/ai/config'),
  demoRun: () => call<unknown>('POST', '/demo/run'),
  disputes: () => call<DisputeSummary[]>('GET', '/disputes'),
  dispute: (id: string) => call<DisputeDetail>('GET', `/disputes/${id}`),
  draftDispute: (id: string, option: string) => call<{ text: string; source: string }>('POST', `/disputes/${id}/draft`, { option }),
  respondDispute: (id: string, option: string, note: string) =>
    call<{ case: DisputeCase; assessment: DisputeAssessment }>('POST', `/disputes/${id}/respond`, { option, note }),
  simulateDispute: (runId: string, lineage_id: string, reason: string, note: string) =>
    call<{ dispute_id: string }>('POST', `${base(runId)}/disputes/simulate`, { lineage_id, reason, note }),
  simulateResolve: (id: string, outcome_code: string) => call<unknown>('POST', `/disputes/${id}/simulate-resolve`, { outcome_code }),
  returnReceived: (id: string, condition: string, note: string) =>
    call<unknown>('POST', `/disputes/${id}/return-received`, { condition, note }),
  simulateReturn: (id: string) => call<unknown>('POST', `/disputes/${id}/simulate-return`, {}),
  recordDelivery: (d: DeliveryInput) => call<{ verdict: string; problems: string[] }>('POST', '/deliveries', d),
  briefUrl: (id: string) => `/api/disputes/${id}/brief.pdf`,
}

export type FullLedgerEntry = LedgerEntry & { payload: Record<string, unknown>; payload_hash: string }
export type LineageView = { source: 'run' | 'seeded'; lineage_id: string; chain_ok: boolean; first_bad_seq: number | null; entries: FullLedgerEntry[] }
export type MandateJson = Record<string, unknown> & { version: number; auto_threshold: string; vendor_allowlist: string[] }
export type MandateDiffRow = { field: string; before: unknown; after: unknown; removed?: string[]; added?: string[] }
export type RunCalibration = {
  changed: boolean
  changes: string[]
  trust: Record<string, number>
  before: MandateJson
  after: MandateJson | null
  diff: MandateDiffRow[]
}
export type Calibration = {
  created_at: string
  from_lineage: string
  to_lineage: string
  changes: string[]
  trust: Record<string, number>
  before: MandateJson
  after: MandateJson
  diff: MandateDiffRow[]
  parent_digest_linked: boolean
}
