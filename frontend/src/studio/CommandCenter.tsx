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
import { api, ApiError, type PaypalTables, type Reconciliation, type StudioRow } from '../api/client'
import { MandateDiff } from '../features/learn/MandateDiff'
import { LineageDrawer } from '../features/lineage/LineageDrawer'
import { buildAi } from './ai'
import { PaypalDetailDrawer, type PaypalSelection } from './PaypalDetailDrawer'
import { paypalPages, paypalSources } from './paypalReport'
import { reconcilePage, reconcileSource } from './reconcileReport'
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
const shortTime = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' })
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
  text('capture_id', 'Capture ID', 'PayPal capture ID (joins to PayPal Transactions.id)'),
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

const LIVE_INTERVALS = [2, 5, 10] as const

const MONEY = ['amount', 'savings', 'payout_net'] as const

type Row = Record<string, string | number | Date | null>

// One ledger row as Studio holds it: money as numbers, timestamps as Dates.
function toRow(r: StudioRow): Row {
  const out: Row = { ...r }
  for (const k of MONEY) out[k] = r[k] == null ? null : Number(r[k])
  for (const k of DATES) out[k] = out[k] ? new Date(String(out[k])) : null
  return out
}

function toSources(rows: StudioRow[], paypal: PaypalTables | null, recon: Reconciliation | null): AgDataSourcesDefinition {
  // Newest first, so the table grows from the top (the backend already sorts; keep it if rows are merged).
  const data = rows.map(toRow).sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
  // transactions: 'all' lets the live feed add and update rows in place instead of reloading Studio.
  const ledger = { id: 'transactions', name: 'Transactions', description: 'One row per purchase lineage', data, fields, transactions: 'all' as const, primaryKeyField: 'lineage_id' }
  if (!paypal) {
    return { description: 'PactGuard AI procurement runs: one row per purchase, built from the hash-chained evidence ledger.', sources: [ledger] }
  }
  const pp = paypalSources(paypal)
  return {
    description:
      'PactGuard AI procurement runs ("Transactions": one row per purchase, from the hash-chained evidence ledger) next to the merchant ' +
      `PayPal sandbox account's own data (${paypal.source === 'live' ? 'read live from the sandbox' : 'a fixed replay fixture'}): invoices, line items, payments, ` +
      'catalog products, billing plans, the account ledger, payouts and balances. Transactions.capture_id joins to PayPal Transactions.id. Invoices are in USD or EUR and are not converted, so filter by currency before summing money.',
    sources: [ledger, ...pp.sources, ...(recon ? [reconcileSource(recon)] : [])],
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
          format: title('Transactions (click a row for sealed lineage, or Capture ID for PayPal settlement)'),
          dataMapping: { cols: ['created_at', 'source', 'lineage_id', 'order_id', 'capture_id', 'vendor', 'category', 'route', 'amount', 'savings', 'status', 'dispute_outcome', 'blocked_reasons'].map((id) => ({ id: f(id) })) },
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
    {
      id: 'activity',
      widgets: {
        decisions: { type: 'value', format: title('Firewall decisions'), dataMapping: { value: [{ id: f('lineage_id'), aggregation: 'count' }] } },
        autoSettled: { type: 'value', format: title('Auto-settled'), dataMapping: { value: [{ id: f('lineage_id'), aggregation: 'count' }] } },
        escalated: { type: 'value', format: title('Escalated to human'), dataMapping: { value: [{ id: f('lineage_id'), aggregation: 'count' }] } },
        avgLatency: { type: 'value', format: title('Avg firewall latency (ms)'), dataMapping: { value: [{ id: f('firewall_ms'), aggregation: 'avg' }] } },
        activityByDay: {
          type: 'column-chart-stacked',
          format: withLegend('Agent decisions by day and route'),
          dataMapping: { categoryKey: [{ id: `${f('created_at')}::day` }], legendKey: [{ id: f('route') }], valueKey: [{ id: f('lineage_id'), aggregation: 'count' }] },
        },
        latencyByRoute: {
          type: 'bar-chart-grouped',
          format: withLegend('Firewall latency by route (avg vs max ms)'),
          dataMapping: {
            categoryKey: [{ id: f('route') }],
            valueKey: [{ id: f('firewall_ms'), aggregation: 'avg' }, { id: f('firewall_ms'), aggregation: 'max' }],
          },
        },
        humanOverrides: {
          type: 'donut-chart',
          format: withLegend('Human escalation outcomes (approved vs rejected)'),
          dataMapping: { categoryKey: [{ id: f('status') }], valueKey: [{ id: f('lineage_id'), aggregation: 'count' }] },
        },
        winOddsByVendor: {
          type: 'bar-chart-grouped',
          format: title('Dispute win odds by supplier'),
          dataMapping: { categoryKey: [{ id: f('vendor') }], valueKey: [{ id: f('dispute_win_odds'), aggregation: 'avg' }] },
        },
        escalations: {
          type: 'grid',
          format: title('Escalations & blocked proposals (click any row for sealed lineage)'),
          dataMapping: {
            cols: ['created_at', 'lineage_id', 'vendor', 'category', 'action', 'route', 'amount', 'firewall_ms', 'status', 'approved_by', 'blocked_reasons', 'dispute_win_odds', 'capture_id'].map((id) => ({ id: f(id) })),
          },
          sort: [{ field: { id: f('created_at') }, direction: 'desc' }],
        },
      },
      filter: {
        widget: {
          autoSettled: only('route', { operator: 'equals', value: 'AUTO_SETTLE' }),
          escalated: only('route', { operator: 'equals', value: 'HUMAN_APPROVAL' }),
          humanOverrides: only('route', { operator: 'equals', value: 'HUMAN_APPROVAL' }),
          winOddsByVendor: only('dispute_win_odds', { operator: 'isNotBlank' }),
          escalations: only('route', { operator: 'notEqual', value: 'AUTO_SETTLE' }),
        },
      },
      widgetLayout: {
        decisions: { xTrack: 0, yTrack: 0, xSpan: 6, ySpan: 7 },
        autoSettled: { xTrack: 6, yTrack: 0, xSpan: 6, ySpan: 7 },
        escalated: { xTrack: 12, yTrack: 0, xSpan: 6, ySpan: 7 },
        avgLatency: { xTrack: 18, yTrack: 0, xSpan: 6, ySpan: 7 },
        activityByDay: { xTrack: 0, yTrack: 7, xSpan: 12, ySpan: 16 },
        latencyByRoute: { xTrack: 12, yTrack: 7, xSpan: 12, ySpan: 16 },
        humanOverrides: { xTrack: 0, yTrack: 23, xSpan: 12, ySpan: 14 },
        winOddsByVendor: { xTrack: 12, yTrack: 23, xSpan: 12, ySpan: 14 },
        escalations: { xTrack: 0, yTrack: 37, xSpan: 24, ySpan: 22 },
      },
    },
  ],
}

// Studio keeps no page names and draws no page tabs; the host does both.
const PAGE_TITLES: Record<string, string> = {
  overview: 'Purchases',
  activity: 'Agent Activity',
  reconciliation: 'Reconciliation',
  revenue: 'Revenue',
  receivables: 'Receivables',
  cash: 'Cash',
  catalogue: 'Catalogue',
}

const AGENT_PAGES = new Set(['overview', 'activity', 'reconciliation'])

const PAGE_HINTS: Record<string, string> = {
  overview: 'Click a purchase row to trace its sealed lineage, or click a Capture ID to inspect its PayPal transaction.',
  activity: 'Derived directly from the hash-chained ledger: firewall decisions, firewall latency, human overrides and escalations.',
  reconciliation: 'Each captured agent purchase against the PayPal account ledger, matched by capture ID. Simulated rows (seeded history, replay) have no PayPal object by design.',
  revenue: 'Merchant PayPal invoices and collections (filter by currency above). Click an invoice row to inspect line items and payments.',
  receivables: 'Open and overdue PayPal invoices by aging bucket. Click an invoice row to inspect customer and payment history.',
  cash: 'PayPal account balances, payout campaigns and 31-day Transaction Search ledger. Click any row to inspect transaction and linked agent purchase.',
  catalogue: 'Merchant PayPal subscription products and billing plans normalised to monthly recurring price.',
}

const pageFromHash = (): string => {
  const m = location.hash.match(/^#\/studio\/([a-z-]+)$/)
  return m ? m[1] : 'overview'
}

// One report with page tabs: the purchase ledger's overview & activity first, then the PayPal account pages when they loaded.
const reportWith = (paypal: PaypalTables | null, recon: Reconciliation | null, requestedPageId: string): AgReportState => {
  const agent = report.pages ?? []
  const pages = paypal ? [...agent, ...(recon ? [reconcilePage] : []), ...paypalPages] : agent
  const selectedPageId = pages.some((p) => p.id === requestedPageId) ? requestedPageId : 'overview'
  // Studio's own panels start stowed so the report is what opens first, as in the AG Studio Report Builder demo.
  const panels = { ai: { collapsed: true }, filters: { collapsed: true }, edit: { collapsed: true }, data: { collapsed: true } }
  return { ...report, selectedPageId, pages, panels }
}

export default function CommandCenter({ runId }: { runId?: string } = {}) {
  const [rows, setRows] = useState<StudioRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<AgStudioMode>('view')
  const [lineage, setLineage] = useState<string | null>(null)
  const [paypalSel, setPaypalSel] = useState<PaypalSelection | null>(null)
  const [diff, setDiff] = useState(false)
  // Studio reads `ai` once, when it is created, so the assistant is decided before it mounts:
  // undefined = still asking the server, null = no key configured (the assistant stays hidden).
  const [aiModel, setAiModel] = useState<string | null | undefined>(undefined)
  // Studio reads its data and initialState once, when it is created, so everything loads before it mounts.
  // The PayPal tables are optional: if the sandbox read fails, the purchase ledger still shows.
  const [paypal, setPaypal] = useState<PaypalTables | null | undefined>(undefined)
  const [recon, setRecon] = useState<Reconciliation | null>(null)
  const [refreshingPaypal, setRefreshingPaypal] = useState(false)
  const apiRef = useRef<AgStudioApi | null>(null)
  const [pageId, setPageId] = useState(pageFromHash)
  const [liveReportingNotice, setLiveReportingNotice] = useState<string | null>(null)
  const [paypalError, setPaypalError] = useState<string | null>(null)
  // Live feed: new and changed purchases reach Studio as data transactions, so widgets update without a reload.
  const [live, setLive] = useState(true)
  const [liveEvery, setLiveEvery] = useState<(typeof LIVE_INTERVALS)[number]>(LIVE_INTERVALS[1])
  const [liveUpdates, setLiveUpdates] = useState(0)
  const [liveError, setLiveError] = useState(false)
  const seen = useRef(new Map<string, string>()) // lineage_id -> last row sent, to tell new rows from changed ones

  const loadRows = useCallback(() => {
    api
      .studioRows(runId, true)
      .then((r) => {
        setError(null)
        setRows(r.rows)
      })
      .catch((e) => setError(String(e)))
  }, [runId])

  // The reconciliation table is derived from the same PayPal read, so both are set together. It is optional:
  // if it fails, the other pages still render without that tab.
  const settle = useCallback(
    (p: PaypalTables, notice: string | null) =>
      api
        .studioReconciliation(p.source === 'replay')
        .catch(() => null)
        .then((r) => {
          setPaypalError(null)
          setPaypal(p)
          setRecon(r)
          setLiveReportingNotice(notice)
        }),
    [],
  )

  const loadPaypal = useCallback(
    (refresh = false) => {
      api
        .studioPaypal(false, refresh)
        .then((p) => settle(p, null))
        .catch((e) => {
          // Only a permission failure (403, e.g. Transaction Search not enabled on the sandbox app) falls back to the fixture.
          // Anything else is shown as an error with Retry, so a real outage is never passed off as replay data.
          if (!(e instanceof ApiError && e.status === 403)) {
            setPaypal(null)
            setRecon(null)
            setPaypalError(String(e))
            return
          }
          return api
            .studioPaypal(true)
            .then((p) => settle(p, 'sandbox app lacks permission for the live read'))
            .catch((e2) => {
              setPaypal(null)
              setRecon(null)
              setPaypalError(String(e2))
            })
        })
        .finally(() => setRefreshingPaypal(false))
    },
    [settle],
  )

  useEffect(() => {
    loadPaypal(false)
  }, [loadPaypal])
  useEffect(loadRows, [loadRows])
  useEffect(() => {
    api.aiConfig().then((c) => setAiModel(c.configured ? c.model : null)).catch(() => setAiModel(null))
  }, [])

  const selectPage = useCallback((id: string, updateHash = true) => {
    setPageId(id)
    const studioApi = apiRef.current
    if (studioApi) studioApi.setState({ ...studioApi.getState(), selectedPageId: id })
    if (updateHash) {
      const target = id === 'overview' ? '#/studio' : `#/studio/${id}`
      if (location.hash !== target) history.replaceState(null, '', target)
    }
  }, [])

  useEffect(() => {
    const onHash = () => {
      if (location.hash === '#/studio' || location.hash.startsWith('#/studio/')) {
        selectPage(pageFromHash(), false)
      }
    }
    addEventListener('hashchange', onHash)
    return () => removeEventListener('hashchange', onHash)
  }, [selectPage])

  const data = useMemo(() => (rows && paypal !== undefined ? toSources(rows, paypal, recon) : null), [rows, paypal, recon])
  const initialState = useMemo(() => reportWith(paypal ?? null, recon, pageId), [paypal, recon, pageId])
  const ai = useMemo(() => (aiModel ? buildAi(aiModel) : undefined), [aiModel])

  useEffect(() => {
    if (rows && seen.current.size === 0) for (const r of rows) seen.current.set(r.lineage_id, JSON.stringify(r))
  }, [rows])

  useEffect(() => {
    if (!live) return
    let stopped = false
    const tick = async () => {
      const engine = (apiRef.current as unknown as { getDataEngine?: () => { applyTransaction?: (tx: unknown) => Promise<unknown> } })?.getDataEngine?.()
      if (!engine?.applyTransaction || document.hidden || seen.current.size === 0) return
      try {
        const latest = (await api.studioRows(runId, true)).rows
        const add: Row[] = []
        const update: Row[] = []
        const next = new Map(seen.current)
        for (const r of latest) {
          const sig = JSON.stringify(r)
          const before = next.get(r.lineage_id)
          if (before === undefined) add.push(toRow(r))
          else if (before !== sig) update.push(toRow(r))
          next.set(r.lineage_id, sig)
        }
        if (stopped) return
        if (add.length || update.length) {
          await engine.applyTransaction({ tableId: 'transactions', ...(add.length ? { add } : {}), ...(update.length ? { update } : {}) })
          setLiveUpdates((n) => n + add.length + update.length)
        }
        seen.current = next // only after Studio accepted it, so a failed batch is retried
        setLiveError(false)
      } catch {
        setLiveError(true)
      }
    }
    const timer = setInterval(tick, liveEvery * 1000)
    return () => {
      stopped = true
      clearInterval(timer)
    }
  }, [live, liveEvery, runId])

  if (error)
    return (
      <div className="m-6 flex items-center justify-between rounded border border-rose-300 bg-rose-50 p-3 text-sm text-rose-800">
        <span>Studio data failed: {error}</span>
        <button className="rounded bg-rose-700 px-3 py-1 text-xs font-medium text-white hover:bg-rose-800" onClick={loadRows}>
          Retry
        </button>
      </div>
    )
  if (!data || !rows || aiModel === undefined || paypal === undefined)
    return (
      <div className="m-6 space-y-4" aria-busy="true">
        <p className="text-sm text-slate-500">Loading Studio data…</p>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-lg border border-slate-200 bg-white p-4" />
          ))}
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="h-56 animate-pulse rounded-lg border border-slate-200 bg-white" />
          <div className="h-56 animate-pulse rounded-lg border border-slate-200 bg-white" />
        </div>
        <div className="h-64 animate-pulse rounded-lg border border-slate-200 bg-white" />
      </div>
    )
  if (rows.length === 0)
    return (
      <div className="m-6 space-y-2 text-sm">
        <p>The ledger has no purchases yet.</p>
        <button className="rounded bg-indigo-600 px-3 py-1.5 font-medium text-white" onClick={() => api.demoRun().then(loadRows)}>
          Run the replay demo
        </button>
      </div>
    )

  const knownTxnIds = new Set([
    ...(paypal?.transactions.map((t) => String(t.id)) ?? []),
    ...rows.map((r) => r.capture_id).filter((id): id is string => !!id),
  ])
  const knownInvoices = new Set(paypal?.invoices.map((i) => String(i.number)) ?? [])

  // Studio has no row-click event, so inspect the clicked cell and row to open the right detail drawer.
  const onGridClick = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement
    const cellText = target.closest('[role="gridcell"]')?.textContent?.trim()
    if (cellText && knownTxnIds.has(cellText) && paypal) {
      setDiff(false)
      setLineage(null)
      setPaypalSel({ kind: 'transaction', id: cellText })
      return
    }
    const row = target.closest('[role="row"]')
    const textContent = row?.textContent ?? ''
    const lid = textContent.match(/PG-[0-9a-f]{16}\.[0-9a-f]{10}/)?.[0]
    if (lid) {
      setDiff(false)
      setPaypalSel(null)
      setLineage(lid)
      return
    }
    if (!paypal) return
    const invNo = textContent.match(/PG-\d{4}/)?.[0]
    if (invNo && knownInvoices.has(invNo)) {
      setDiff(false)
      setLineage(null)
      setPaypalSel({ kind: 'invoice', id: invNo })
      return
    }
    const txnMatch = textContent.match(/TXN-FIXT-\d{4}|CAP-\d{6}|[0-9A-Z]{17}/)?.[0]
    if (txnMatch && knownTxnIds.has(txnMatch)) {
      setDiff(false)
      setLineage(null)
      setPaypalSel({ kind: 'transaction', id: txnMatch })
    }
  }

  const allPages = initialState.pages ?? []
  const agentPages = allPages.filter((p) => AGENT_PAGES.has(p.id))
  const accountPages = allPages.filter((p) => !AGENT_PAGES.has(p.id))

  const onTabKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return
    e.preventDefault()
    const ids = allPages.map((p) => p.id)
    const idx = ids.indexOf(pageId)
    if (idx === -1) return
    const nextIdx =
      e.key === 'Home' ? 0 : e.key === 'End' ? ids.length - 1 : (idx + (e.key === 'ArrowRight' ? 1 : -1) + ids.length) % ids.length
    const nextId = ids[nextIdx]
    selectPage(nextId)
    const btn = e.currentTarget.querySelector<HTMLButtonElement>(`[data-page-tab="${nextId}"]`)
    btn?.focus()
  }

  const renderTab = (id: string) => (
    <button
      key={id}
      data-page-tab={id}
      role="tab"
      tabIndex={id === pageId ? 0 : -1}
      aria-selected={id === pageId}
      className={`-mb-px whitespace-nowrap border-b-2 px-3 py-1.5 text-sm font-medium ${id === pageId ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-600 hover:text-slate-900'}`}
      onClick={() => selectPage(id)}
    >
      {PAGE_TITLES[id] ?? id}
    </button>
  )

  return (
    <div className="flex h-full flex-col">
      <div
        className="flex flex-wrap items-center gap-x-3 gap-y-1 overflow-x-auto border-b border-slate-200 bg-white px-6 pt-1.5"
        role="group"
        aria-label="Report pages"
        onKeyDown={onTabKeyDown}
      >
        <div className="flex items-center gap-1" role="tablist" aria-label="Agent pages">
          <span aria-hidden="true" className="mr-1 rounded bg-indigo-50 px-1.5 py-0.5 text-[11px] font-semibold tracking-wide text-indigo-700 uppercase">
            Agent
          </span>
          {agentPages.map((p) => renderTab(p.id))}
        </div>
        {accountPages.length > 0 && (
          <div className="flex items-center gap-1 border-l border-slate-200 pl-3" role="tablist" aria-label="PayPal account pages">
            <span aria-hidden="true" className="mr-1 rounded bg-sky-50 px-1.5 py-0.5 text-[11px] font-semibold tracking-wide text-sky-800 uppercase">
              PayPal account
            </span>
            {accountPages.map((p) => renderTab(p.id))}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-white px-6 py-1.5">
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span>{PAGE_HINTS[pageId] ?? PAGE_HINTS.overview}</span>
          {paypal && (
            <span className="inline-flex items-center gap-1.5">
              <span
                className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                  paypal.source === 'live' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
                }`}
                title={liveReportingNotice ?? undefined}
              >
                {paypal.source === 'live' ? 'Live sandbox' : 'Replay fixture'}
                {liveReportingNotice ? ` (${liveReportingNotice})` : ''}
              </span>
              <span className="text-slate-400">as of {shortTime.format(new Date(paypal.asOf))}</span>
              <button
                className="rounded border border-slate-200 px-1.5 py-0.5 text-[11px] font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-50"
                disabled={refreshingPaypal}
                onClick={() => {
                  setRefreshingPaypal(true)
                  loadRows()
                  loadPaypal(true)
                }}
              >
                {refreshingPaypal ? 'Refreshing…' : 'Refresh'}
              </button>
            </span>
          )}
          {!paypal && paypalError && (
            <span className="inline-flex items-center gap-2 text-rose-700">
              <span>PayPal pages unavailable: {paypalError}</span>
              <button
                className="rounded border border-rose-300 bg-rose-50 px-2 py-0.5 text-[11px] font-medium text-rose-800 hover:bg-rose-100"
                onClick={() => {
                  setRefreshingPaypal(true)
                  loadPaypal(true)
                }}
              >
                Retry PayPal
              </button>
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-1">
          <span className="inline-flex items-center gap-1.5 text-xs" role="status">
            <span
              aria-hidden="true"
              className={`h-2 w-2 rounded-full ${liveError ? 'bg-rose-500' : live ? 'animate-pulse bg-emerald-500' : 'bg-slate-300'}`}
            />
            <span className="font-medium text-slate-700">{liveError ? 'Feed error, retrying' : live ? 'Live' : 'Paused'}</span>
            {liveUpdates > 0 && <span className="text-slate-400">{liveUpdates} update{liveUpdates === 1 ? '' : 's'}</span>}
          </span>
          <button
            className="rounded px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100"
            onClick={() => setLive(!live)}
          >
            {live ? 'Pause' : 'Resume'}
          </button>
          <label className="flex items-center gap-1 text-xs text-slate-500">
            every
            <select
              className="rounded border border-slate-200 bg-white px-1 py-0.5 text-xs"
              value={liveEvery}
              onChange={(e) => setLiveEvery(Number(e.target.value) as (typeof LIVE_INTERVALS)[number])}
            >
              {LIVE_INTERVALS.map((s) => (
                <option key={s} value={s}>
                  {s}s
                </option>
              ))}
            </select>
          </label>
          <button
            className="rounded px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100"
            onClick={() => {
              setLineage(null)
              setPaypalSel(null)
              setDiff(!diff)
            }}
          >
            Mandate v1 → v2
          </button>
          <button
            className="rounded px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100"
            onClick={() => setMode(mode === 'view' ? 'edit' : 'view')}
          >
            {mode === 'view' ? 'Edit report' : 'Done editing'}
          </button>
        </div>
      </div>

      <div className="relative min-h-0 flex-1" onClick={onGridClick}>
        <AgStudioProvider licenseKey={licenseKey} modules={ai ? modules : undefined}>
          <AgStudio
            style={{ height: '100%', width: '100%' }}
            theme={pactguardTheme}
            layout={{ widgetBorderEnabled: true }}
            panels={{ edit: { left: ai ? ['ai'] : [], right: ['filters', 'edit', 'data'] }, view: { right: ['filters'] } }}
            data={data}
            initialState={initialState}
            mode={mode}
            ai={ai}
            onApiReady={(e) => {
              apiRef.current = e.api
            }}
            onStateUpdated={(e) => setPageId(e.state.selectedPageId)}
          />
        </AgStudioProvider>
        {lineage && (
          <LineageDrawer
            key={lineage}
            lineage={lineage}
            onClose={() => setLineage(null)}
            onOpenPaypalTxn={
              paypal
                ? (captureId) => {
                    setLineage(null)
                    setPaypalSel({ kind: 'transaction', id: captureId })
                  }
                : undefined
            }
          />
        )}
        {paypalSel && paypal && (
          <PaypalDetailDrawer
            key={`${paypalSel.kind}:${paypalSel.id}`}
            selection={paypalSel}
            paypal={paypal}
            rows={rows}
            onClose={() => setPaypalSel(null)}
            onOpenLineage={(lid) => {
              setPaypalSel(null)
              setLineage(lid)
            }}
          />
        )}
        {diff && <MandateDiff runId={runId} onClose={() => setDiff(false)} />}
      </div>
    </div>
  )
}
