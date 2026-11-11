// The "Reconciliation" page: each captured agent purchase against the PayPal account ledger, from
// GET /api/studio/reconciliation (derived in backend/app/studio_reconcile.py, not in the browser).

import type { AgDataSourcesDefinition, AgFilterState, AgPageState } from 'ag-studio'
import type { Reconciliation } from '../api/client'
import { at, countd, fields, kpi, sum, title } from './paypalReport'

const R = 'reconciliation'
const col = (id: string) => `${R}.${id}`

export const RECONCILIATION_STATUSES = ['Matched', 'Amount mismatch', 'Pending', 'Outside window', 'Unsettled', 'Simulated', 'Not decided by agent']

type AgDataSource = NonNullable<AgDataSourcesDefinition['sources']>[number]

export const reconcileSource = (data: Reconciliation): AgDataSource => ({
  id: R,
  name: 'Agent vs PayPal',
  description:
    'One row per captured agent purchase, matched to the PayPal account ledger by capture ID, plus purchase captures PayPal shows that the agent never decided. ' +
    '"Status": Matched (same amount), Amount mismatch, Pending (captured in the last few hours, Transaction Search may lag), Outside window (older than the 31 days Transaction Search covers), ' +
    'Unsettled (no PayPal transaction inside the window), Simulated (seeded history or replay: no PayPal object exists) or Not decided by agent. Amounts are positive here; agent amount is what the ledger sealed, PayPal amount is what PayPal shows.',
  data: data.rows,
  fields: fields([
    ['id', 'Capture ID', 'textFormat'],
    ['lineageId', 'Lineage ID', 'textFormat'],
    ['origin', 'Agent Source', 'textFormat', true],
    ['vendor', 'Vendor / Counterparty', 'textFormat'],
    ['category', 'Category', 'textFormat'],
    ['date', 'Captured', 'dateTimeFormat'],
    ['agentAmount', 'Agent Amount', 'currencyFormat'],
    ['paypalAmount', 'PayPal Amount', 'currencyFormat'],
    ['paypalFee', 'PayPal Fee', 'currencyFormat'],
    ['netCash', 'Net Cash Impact', 'currencyFormat'],
    ['difference', 'Difference', 'currencyFormat'],
    ['status', 'Reconciliation Status', 'textFormat'],
    ['note', 'What it means', 'textFormat'],
    ['paypalId', 'PayPal Transaction ID', 'textFormat', true],
  ]),
})

const only = (model: AgFilterState['model']): AgFilterState[] => [{ field: { id: col('status') }, model }]

export const reconcilePage: AgPageState = {
  id: 'reconciliation',
  widgets: {
    'kpi-matched': kpi('Matched in PayPal', countd(col('id'))),
    'kpi-attention': kpi('Needs attention', countd(col('id'))),
    'kpi-fees': kpi('PayPal fees', sum(col('paypalFee'))),
    'kpi-net': kpi('Net cash impact', sum(col('netCash'))),
    'status-donut': {
      type: 'donut-chart',
      dataMapping: { categoryKey: [{ id: col('status') }], valueKey: [countd(col('id'))] },
      format: { ...title('Captures by reconciliation status'), style: { custom: { pieDataLabel: { enabled: true }, totalLabel: { enabled: true } } } },
    },
    'status-by-vendor': {
      type: 'bar-chart-stacked',
      dataMapping: { categoryKey: [{ id: col('vendor') }], legendKey: [{ id: col('status') }], valueKey: [countd(col('id'))] },
      format: { ...title('Status by vendor'), style: { theme: { common: { legend: { enabled: true, position: 'bottom' } } } } },
    },
    captures: {
      type: 'grid',
      dataMapping: {
        cols: ['date', 'id', 'lineageId', 'vendor', 'category', 'agentAmount', 'paypalAmount', 'difference', 'paypalFee', 'netCash', 'status', 'note'].map((id) => ({ id: col(id) })),
      },
      sort: [{ field: { id: col('date') }, direction: 'desc' }],
      format: title('Captures against the PayPal ledger (click a row for lineage or PayPal detail)'),
    },
  },
  filter: {
    widget: {
      'kpi-matched': only({ operator: 'equals', value: 'Matched' }),
      'kpi-attention': only({ operator: 'isIn', value: ['Amount mismatch', 'Unsettled', 'Not decided by agent'] }),
    },
  },
  widgetLayout: {
    'kpi-matched': at(0, 0, 6, 7),
    'kpi-attention': at(6, 0, 6, 7),
    'kpi-fees': at(12, 0, 6, 7),
    'kpi-net': at(18, 0, 6, 7),
    'status-donut': at(0, 7, 10, 16),
    'status-by-vendor': at(10, 7, 14, 16),
    captures: at(0, 23, 24, 26),
  },
}
