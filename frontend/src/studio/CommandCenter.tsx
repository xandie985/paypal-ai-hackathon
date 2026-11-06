import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AgStudioAiModule,
  enableStudioDevValidations,
  type AgDataSourcesDefinition,
  type AgFieldDefinition,
  type AgFilterOperator,
  type AgFilterState,
  type AgReportState,
  type AgStudioApi,
  type AgStudioMode,
} from 'ag-studio'
import { AgStudio, AgStudioProvider } from 'ag-studio-react'
import { api, type PaypalTables, type StudioRow } from '../api/client'
import { MandateDiff } from '../features/learn/MandateDiff'
import { LineageDrawer } from '../features/lineage/LineageDrawer'
import { buildAi } from './ai'
import { paypalPages, paypalSources } from './paypalReport'
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

const when = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'medium' })
const datetime = (id: string, name: string, description: string): AgFieldDefinition => ({
  id,
  name,
  description,
  format: 'dateTimeFormat',
  formatOptions: { format: when },
})
const DATES = ['created_at', 'updated_at'] as const

const pctFmt = new Intl.NumberFormat('en-US', { style: 'percent', maximumFractionDigits: 0 })
const percent = (id: string, name: string, description: string): AgFieldDefinition => ({
  id,
  name,
  description,
  format: 'percentageFormat',
  formatOptions: { format: pctFmt },
})

const fields: AgFieldDefinition[] = [
  datetime('created_at', 'Time', 'When the agent first proposed this purchase (sealed ledger time, shown in your time zone)'),
  datetime('updated_at', 'Last update', 'Time of the latest ledger entry for this purchase (approval, capture, dispute…)'),
  text('lineage_id', 'Lineage ID', 'PG-… ID shared by every ledger entry for one purchase'),
  text('source', 'Source', 'run = the current mandate; seeded = synthetic history run through the same code path'),
  text('order_id', 'Order ID', 'PayPal order ID'),
  text('capture_id', 'Capture ID', 'PayPal capture ID'),
  text('vendor', 'Vendor', 'Seller the agent bought from or proposed to buy from'),
  text('category', 'Category', 'Product category from the mandate'),
  text('action', 'Action', 'What the agent proposed (buy or negotiate)'),
  text('route', 'Route', 'Firewall outcome: AUTO_SETTLE, HUMAN_APPROVAL or BLOCKED'),
  money('amount', 'Amount', 'Proposed purchase total in USD (unit price × quantity)'),
  money('savings', 'Savings', 'Saving against the retail baseline in USD'),
  { id: 'firewall_ms', name: 'Firewall ms', description: 'Firewall decision latency in milliseconds', format: 'integerFormat' },
  text('status', 'Status', 'CAPTURED once PayPal captured the payment, REJECTED if a human declined it'),
  text('approved_by', 'Approved by', 'Human approver for HUMAN_APPROVAL purchases'),
  text('delivery', 'Delivery', 'Delivery proof verdict'),
  text('invoice_status', 'Invoice', 'Reconciliation status of the PayPal invoice'),
  money('payout_net', 'Payout net', 'Net amount paid out to the supplier'),
  text('dispute_outcome', 'Dispute', 'WON, LOST (contested and lost) or SETTLED (we offered the refund)'),
  text('blocked_reasons', 'Blocked reasons', 'Why the firewall blocked the purchase'),
  percent('supplier_trust', 'Supplier trust', 'Stage 10 score per vendor (0-100%): delivery PASS and disputes WON raise it; failed or late deliveries and LOST or SETTLED disputes lower it. A new supplier starts at 67%.'),
  percent('dispute_win_odds', 'Dispute win odds', 'The desk\'s estimated odds when it answered this purchase\'s dispute'),
]

const MONEY = ['amount', 'savings', 'payout_net'] as const

function toSources(rows: StudioRow[], paypal: PaypalTables | null): AgDataSourcesDefinition {
  const data = rows.map((r) => {
    const out: Record<string, string | number | Date | null> = { ...r }
    for (const k of MONEY) out[k] = r[k] == null ? null : Number(r[k])
    return out
  })
  // Newest first, so the table grows from the top (the backend already sorts; keep it if rows are merged).
  data.sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
  for (const row of data) for (const k of DATES) row[k] = row[k] ? new Date(String(row[k])) : null
  const ledger = { id: 'transactions', name: 'Transactions', description: 'One row per purchase lineage', data, fields }
  if (!paypal) {
    return { description: 'PactGuard AI procurement runs: one row per purchase, built from the hash-chained evidence ledger.', sources: [ledger] }
  }
  const pp = paypalSources(paypal)
  return {
    description:
      'PactGuard AI procurement runs ("Transactions": one row per purchase, from the hash-chained evidence ledger) next to the merchant ' +
      `PayPal sandbox account's own data (${paypal.source === 'live' ? 'read live from the sandbox' : 'a fixed replay fixture'}): invoices, line items, payments, ` +
      'catalog products, billing plans, the account ledger, payouts and balances. Invoices are in USD or EUR and are not converted, so filter by currency before summing money.',
    sources: [ledger, ...pp.sources],
    relationships: pp.relationships,
    calendars: pp.calendars,
    expressions: pp.expressions,
  }
}

const title = (t: string) => ({ title: { text: t, enabled: true } })
// Charts split by a legend field need the legend, or the colours mean nothing.
const withLegend = (t: string) => ({ ...title(t), style: { theme: { common: { legend: { enabled: true, position: 'bottom' as const } } } } })
const CAPTURED = { operator: 'equals' as const, value: 'CAPTURED' }
const f = (id: string) => `transactions.${id}`
const only = (id: string, model: { operator: AgFilterOperator; value?: unknown }): AgFilterState[] => [{ field: { id: f(id) }, model }]

const report: AgReportState = {
  selectedPageId: 'overview',
  pages: [
    {
      id: 'overview',
      widgets: {
        spend: { type: 'value', format: title('Captured spend'), dataMapping: { value: [{ id: f('amount'), aggregation: 'sum' }] } },
        savings: { type: 'value', format: title('Saved vs retail (captured)'), dataMapping: { value: [{ id: f('savings'), aggregation: 'sum' }] } },
        count: { type: 'value', format: title('Purchases'), dataMapping: { value: [{ id: f('lineage_id'), aggregation: 'count' }] } },
        blocked: { type: 'value', format: title('Blocked by the firewall'), dataMapping: { value: [{ id: f('lineage_id'), aggregation: 'count' }] } },
        // Widget 1: what negotiation and discovery saved, by vendor, split by category. Only captured purchases:
        // blocked and rejected proposals never happened.
        savingsByVendor: {
          type: 'column-chart-grouped',
          format: withLegend('Saved vs retail, by vendor and category'),
          dataMapping: { categoryKey: [{ id: f('vendor') }], legendKey: [{ id: f('category') }], valueKey: [{ id: f('savings'), aggregation: 'sum' }] },
        },
        // Widget 2: the firewall's decisions over time.
        routesOverTime: {
          type: 'column-chart-stacked',
          format: withLegend('Firewall routes by week'),
          dataMapping: { categoryKey: [{ id: `${f('created_at')}::week` }], legendKey: [{ id: f('route') }], valueKey: [{ id: f('lineage_id'), aggregation: 'count' }] },
        },
        // Widget 3: how disputes ended per supplier, next to the trust score stage 10 learns from them.
        disputes: {
          type: 'bar-chart-stacked',
          format: withLegend('Dispute outcomes by supplier'),
          dataMapping: { categoryKey: [{ id: f('vendor') }], legendKey: [{ id: f('dispute_outcome') }], valueKey: [{ id: f('lineage_id'), aggregation: 'count' }] },
        },
        trust: {
          type: 'bar-chart-grouped',
          format: title('Supplier trust (stage 10)'),
          dataMapping: { categoryKey: [{ id: f('vendor') }], valueKey: [{ id: f('supplier_trust'), aggregation: 'avg' }] },
        },
        table: {
          type: 'grid',
          format: title('Transactions'),
          dataMapping: { cols: ['created_at', 'source', 'lineage_id', 'order_id', 'vendor', 'category', 'route', 'amount', 'savings', 'status', 'dispute_outcome', 'blocked_reasons'].map((id) => ({ id: f(id) })) },
          sort: [{ field: { id: f('created_at') }, direction: 'desc' }], // newest purchase on top
        },
      },
      filter: {
        widget: {
          spend: only('status', CAPTURED),
          savings: only('status', CAPTURED),
          blocked: only('route', { operator: 'equals', value: 'BLOCKED' }),
          savingsByVendor: only('status', CAPTURED),
          disputes: only('dispute_outcome', { operator: 'isNotBlank' }),
          trust: only('supplier_trust', { operator: 'isNotBlank' }),
        },
      },
      widgetLayout: {
        spend: { xTrack: 0, yTrack: 0, xSpan: 6, ySpan: 7 },
        savings: { xTrack: 6, yTrack: 0, xSpan: 6, ySpan: 7 },
        count: { xTrack: 12, yTrack: 0, xSpan: 6, ySpan: 7 },
        blocked: { xTrack: 18, yTrack: 0, xSpan: 6, ySpan: 7 },
        routesOverTime: { xTrack: 0, yTrack: 7, xSpan: 12, ySpan: 16 },
        savingsByVendor: { xTrack: 12, yTrack: 7, xSpan: 12, ySpan: 16 },
        disputes: { xTrack: 0, yTrack: 23, xSpan: 12, ySpan: 14 },
        trust: { xTrack: 12, yTrack: 23, xSpan: 12, ySpan: 14 },
        table: { xTrack: 0, yTrack: 37, xSpan: 24, ySpan: 22 },
      },
    },
  ],
}

// Studio keeps no page names and draws no page tabs; the host does both.
const PAGE_TITLES: Record<string, string> = {
  overview: 'Purchases',
  revenue: 'Revenue',
  receivables: 'Receivables',
  cash: 'Cash',
  catalogue: 'Catalogue',
}

// One report with page tabs: the purchase ledger's overview first, then the PayPal account pages when they loaded.
const reportWith = (paypal: PaypalTables | null): AgReportState => (paypal ? { ...report, pages: [...(report.pages ?? []), ...paypalPages] } : report)

export default function CommandCenter({ runId }: { runId?: string } = {}) {
  const [rows, setRows] = useState<StudioRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<AgStudioMode>('view')
  const [lineage, setLineage] = useState<string | null>(null)
  const [diff, setDiff] = useState(false)
  // Studio reads `ai` once, when it is created, so the assistant is decided before it mounts:
  // undefined = still asking the server, null = no key configured (the assistant stays hidden).
  const [aiModel, setAiModel] = useState<string | null | undefined>(undefined)
  // Studio reads its data and initialState once, when it is created, so everything loads before it mounts.
  // The PayPal tables are optional: if the sandbox read fails, the purchase ledger still shows.
  const [paypal, setPaypal] = useState<PaypalTables | null | undefined>(undefined)
  const apiRef = useRef<AgStudioApi | null>(null)
  const [pageId, setPageId] = useState(report.selectedPageId)
  const [paypalError, setPaypalError] = useState<string | null>(null)
  const load = useCallback(() => {
    api.studioRows(runId, true).then((r) => setRows(r.rows)).catch((e) => setError(String(e)))
  }, [runId])
  useEffect(() => {
    api
      .studioPaypal()
      .then(setPaypal)
      .catch((e) => {
        api
          .studioPaypal(true)
          .then((p) => {
            setPaypal(p)
            setPaypalError(`Live sandbox reporting unavailable (${String(e)}). Showing fixture data.`)
          })
          .catch((e2) => {
            setPaypal(null)
            setPaypalError(String(e2))
          })
      })
  }, [])
  useEffect(load, [load])
  useEffect(() => {
    api.aiConfig().then((c) => setAiModel(c.configured ? c.model : null)).catch(() => setAiModel(null))
  }, [])
  const data = useMemo(() => (rows && paypal !== undefined ? toSources(rows, paypal) : null), [rows, paypal])
  const initialState = useMemo(() => reportWith(paypal ?? null), [paypal])
  const ai = useMemo(() => (aiModel ? buildAi(aiModel) : undefined), [aiModel])

  if (error) return <p className="m-6 rounded border border-rose-300 bg-rose-50 p-2 text-sm text-rose-800">Studio data failed: {error}</p>
  if (!data || !rows || aiModel === undefined || paypal === undefined) return <p className="m-6 text-sm text-slate-500">Loading Studio data…</p>
  if (rows.length === 0)
    return (
      <div className="m-6 space-y-2 text-sm">
        <p>The ledger has no purchases yet.</p>
        <button className="rounded bg-indigo-600 px-3 py-1.5 font-medium text-white" onClick={() => api.demoRun().then(load)}>
          Run the replay demo
        </button>
      </div>
    )

  // Studio has no row-click event, so read the purchase's lineage ID off the clicked grid row.
  const onGridClick = (e: React.MouseEvent) => {
    const row = (e.target as HTMLElement).closest('[role="row"]')
    const id = row?.textContent?.match(/PG-[0-9a-f]{16}\.[0-9a-f]{10}/)?.[0]
    if (id) {
      setDiff(false)
      setLineage(id)
    }
  }

  const selectPage = (id: string) => {
    const api = apiRef.current
    if (api) api.setState({ ...api.getState(), selectedPageId: id })
  }

  return (
    <div className="flex h-full flex-col">
      {paypal && (
        <div className="flex gap-1 border-b border-slate-200 bg-white px-6 pt-1.5" role="tablist" aria-label="Report pages">
          {(initialState.pages ?? []).map((p) => (
            <button
              key={p.id}
              role="tab"
              aria-selected={p.id === pageId}
              className={`-mb-px border-b-2 px-3 py-1.5 text-sm font-medium ${p.id === pageId ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-600 hover:text-slate-900'}`}
              onClick={() => selectPage(p.id)}
            >
              {PAGE_TITLES[p.id] ?? p.id}
            </button>
          ))}
        </div>
      )}
      <div className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-1.5">
        <span className="text-xs text-slate-500">
          Click a purchase row to trace its sealed lineage.
          {paypal && <> PayPal pages: {paypal.source === 'live' ? 'live sandbox account' : 'replay fixture'}.</>}
          {paypalError && <span className="text-rose-700"> PayPal pages unavailable: {paypalError}</span>}
        </span>
        <div className="flex gap-1">
          <button
            className="rounded px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100"
            onClick={() => {
              setLineage(null)
              setDiff(!diff)
            }}
          >
            Mandate v1 → v2
          </button>
          <button className="rounded px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100" onClick={() => setMode(mode === 'view' ? 'edit' : 'view')}>
            {mode === 'view' ? 'Edit report' : 'Done editing'}
          </button>
        </div>
      </div>
      <div className="relative min-h-0 flex-1" onClick={onGridClick}>
        <AgStudioProvider licenseKey={licenseKey} modules={ai ? modules : undefined}>
          <AgStudio style={{ height: '100%', width: '100%' }} theme={pactguardTheme} data={data} initialState={initialState}
            mode={mode}
            ai={ai}
            onApiReady={(e) => {
              apiRef.current = e.api
            }}
            onStateUpdated={(e) => setPageId(e.state.selectedPageId)}
          />
        </AgStudioProvider>
        {lineage && <LineageDrawer key={lineage} lineage={lineage} onClose={() => setLineage(null)} />}
        {diff && <MandateDiff runId={runId} onClose={() => setDiff(false)} />}
      </div>
    </div>
  )
}
