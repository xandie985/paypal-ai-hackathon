export type Factor = { name: string; passed: boolean; hard: boolean; detail: string }
export type Decision = {
  lineage_id: string
  route: 'AUTO_SETTLE' | 'HUMAN_APPROVAL' | 'BLOCKED'
  factors: Factor[]
  reasons: string[]
  latency_ms: number
}
export type Item = {
  lineage_id: string
  title: string
  method: 'direct' | 'negotiate'
  status: string
  decision: Decision | null
  order_id: string | null
  capture_id: string | null
}
export type RunSnapshot = { run_id: string; mandate_lineage: string; complete: boolean; items: Item[] }
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
  health: () => call<{ replay_mode: boolean; paypal_live: boolean }>('GET', '/health'),
  startRun: (mandate?: MandateInput) => call<RunSnapshot>('POST', '/runs', mandate ? { mandate } : {}),
  getRun: (id: string) => call<RunSnapshot>('GET', base(id)),
  approve: (id: string, lid: string) => call<RunSnapshot>('POST', `${base(id)}/decisions/${lid}/approve`, {}),
  reject: (id: string, lid: string) => call<RunSnapshot>('POST', `${base(id)}/decisions/${lid}/reject`, {}),
  prepare: (id: string, lid: string) => call<{ order_id: string }>('POST', `${base(id)}/orders/${lid}/prepare`),
  capture: (id: string, lid: string) => call<{ capture_id: string }>('POST', `${base(id)}/orders/${lid}/capture`),
  retry: (id: string, lid: string) => call<{ order_id: string; same_order: boolean }>('POST', `${base(id)}/orders/${lid}/retry`),
  attack: (id: string) => call<{ route: string; reasons: string[]; latency_ms: number }>('POST', `${base(id)}/attack`),
  events: (id: string) => new EventSource(`/api${base(id)}/events`),
}
