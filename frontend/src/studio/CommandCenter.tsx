import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AgStudioAiModule,
  enableStudioDevValidations,
  type AgDataSourcesDefinition,
  type AgFieldDefinition,
  type AgReportState,
  type AgStudioMode,
} from 'ag-studio'
import { AgStudio, AgStudioProvider } from 'ag-studio-react'
import { api, type StudioRow } from '../api/client'
import { pactguardTheme } from './theme'

if (import.meta.env.DEV) enableStudioDevValidations()

// The licence key ships in the browser bundle by design (doc 11 §6.2). Unset = local watermark mode.
const licenseKey = import.meta.env.VITE_AG_STUDIO_LICENSE || undefined
const modules = [AgStudioAiModule]

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
const text = (id: string, name: string, description: string): AgFieldDefinition => ({ id, name, description, format: 'textFormat' })
const money = (id: string, name: string, description: string): AgFieldDefinition => ({
  id,
  name,
  description,
  format: 'currencyFormat',
  formatOptions: { format: usd },
})

const fields: AgFieldDefinition[] = [
  text('lineage_id', 'Lineage ID', 'PG-… ID shared by every ledger entry for one purchase'),
  text('vendor', 'Vendor', 'Seller the agent bought from or proposed to buy from'),
  text('category', 'Category', 'Product category from the mandate'),
  text('action', 'Action', 'What the agent proposed (buy or negotiate)'),
  text('route', 'Route', 'Firewall outcome: AUTO_SETTLE, HUMAN_APPROVAL or BLOCKED'),
  money('amount', 'Amount', 'Proposed purchase total in USD (unit price × quantity)'),
  money('savings', 'Savings', 'Saving against the retail baseline in USD'),
  { id: 'firewall_ms', name: 'Firewall ms', description: 'Firewall decision latency in milliseconds', format: 'integerFormat' },
  text('status', 'Status', 'CAPTURED once PayPal captured the payment'),
  text('approved_by', 'Approved by', 'Human approver for HUMAN_APPROVAL purchases'),
  text('delivery', 'Delivery', 'Delivery proof verdict'),
  text('invoice_status', 'Invoice', 'Reconciliation status of the PayPal invoice'),
  money('payout_net', 'Payout net', 'Net amount paid out to the supplier'),
  text('dispute_outcome', 'Dispute', 'WON or LOST when a dispute was raised'),
  text('blocked_reasons', 'Blocked reasons', 'Why the firewall blocked the purchase'),
]

const MONEY = ['amount', 'savings', 'payout_net'] as const

function toSources(rows: StudioRow[]): AgDataSourcesDefinition {
  const data = rows.map((r) => {
    const out: Record<string, string | number | null> = { ...r }
    for (const k of MONEY) out[k] = r[k] == null ? null : Number(r[k])
    return out
  })
  return {
    description: 'PactGuard AI procurement runs: one row per purchase, built from the hash-chained evidence ledger.',
    sources: [{ id: 'transactions', name: 'Transactions', description: 'One row per purchase lineage', data, fields }],
  }
}

const title = (t: string) => ({ title: { text: t, enabled: true } })
const f = (id: string) => `transactions.${id}`

const report: AgReportState = {
  selectedPageId: 'overview',
  pages: [
    {
      id: 'overview',
      widgets: {
        spend: { type: 'value', format: title('Proposed spend'), dataMapping: { value: [{ id: f('amount'), aggregation: 'sum' }] } },
        savings: { type: 'value', format: title('Savings vs retail'), dataMapping: { value: [{ id: f('savings'), aggregation: 'sum' }] } },
        count: { type: 'value', format: title('Purchases'), dataMapping: { value: [{ id: f('lineage_id'), aggregation: 'count' }] } },
        routes: {
          type: 'donut-chart',
          format: title('Firewall routes'),
          dataMapping: { categoryKey: [{ id: f('route') }], valueKey: [{ id: f('lineage_id'), aggregation: 'count' }] },
        },
        table: {
          type: 'grid',
          format: title('Transactions'),
          dataMapping: { cols: ['lineage_id', 'vendor', 'category', 'route', 'amount', 'savings', 'status', 'blocked_reasons'].map((id) => ({ id: f(id) })) },
        },
      },
      widgetLayout: {
        spend: { xTrack: 0, yTrack: 0, xSpan: 8, ySpan: 8 },
        savings: { xTrack: 8, yTrack: 0, xSpan: 8, ySpan: 8 },
        count: { xTrack: 16, yTrack: 0, xSpan: 8, ySpan: 8 },
        routes: { xTrack: 0, yTrack: 8, xSpan: 8, ySpan: 20 },
        table: { xTrack: 8, yTrack: 8, xSpan: 16, ySpan: 20 },
      },
    },
  ],
}

export default function CommandCenter() {
  const [rows, setRows] = useState<StudioRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<AgStudioMode>('view')
  const load = useCallback(() => {
    api.studioRows().then((r) => setRows(r.rows)).catch((e) => setError(String(e)))
  }, [])
  useEffect(load, [load])
  const data = useMemo(() => (rows ? toSources(rows) : null), [rows])

  if (error) return <p className="m-6 rounded border border-rose-300 bg-rose-50 p-2 text-sm text-rose-800">Studio data failed: {error}</p>
  if (!data || !rows) return <p className="m-6 text-sm text-slate-500">Loading Studio data…</p>
  if (rows.length === 0)
    return (
      <div className="m-6 space-y-2 text-sm">
        <p>The ledger has no purchases yet.</p>
        <button className="rounded bg-indigo-600 px-3 py-1.5 font-medium text-white" onClick={() => api.demoRun().then(load)}>
          Run the replay demo
        </button>
      </div>
    )

  return (
    <div className="flex h-full flex-col">
      <div className="flex justify-end border-b border-slate-200 bg-white px-6 py-1.5">
        <button className="rounded px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100" onClick={() => setMode(mode === 'view' ? 'edit' : 'view')}>
          {mode === 'view' ? 'Edit report' : 'Done editing'}
        </button>
      </div>
      <div className="min-h-0 flex-1">
        <AgStudioProvider licenseKey={licenseKey} modules={modules}>
          <AgStudio style={{ height: '100%', width: '100%' }} theme={pactguardTheme} data={data} initialState={report} mode={mode} />
        </AgStudioProvider>
      </div>
    </div>
  )
}
