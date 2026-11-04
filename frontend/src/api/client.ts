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
  studioRows: (runId?: string) =>
    call<{ rows: StudioRow[]; kpis: Record<string, string | number> }>('GET', runId ? `/studio/rows?run_id=${encodeURIComponent(runId)}` : '/studio/rows'),
  demoRun: () => call<unknown>('POST', '/demo/run'),
}
