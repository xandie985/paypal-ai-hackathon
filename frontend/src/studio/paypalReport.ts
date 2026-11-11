// The "PayPal overview" pages of the Command Center: data sources, relationships and four report pages
// (Revenue, Receivables, Cash, Catalogue) over the account tables from GET /api/studio/paypal.
//
// Adapted from paypaldev/hackathon-paypal-ag-grid-boilerplate (app/dashboard/studio/data.ts and
// initial-report.ts). The Transactions source of the purchase ledger already owns that id here, so the
// account ledger is "paypalTransactions" ("PayPal Transactions").

import type {
  AgDataSourcesDefinition,
  AgExpressionFieldDefinition,
  AgFieldDefinition,
  AgFormat,
  AgPageState,
  AgRelationDefinition,
  AgWidgetLayoutState,
} from 'ag-studio'
import type { PaypalTables } from '../api/client'

const CALENDAR_ID = 'calendar'
const TXN = 'paypalTransactions'

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
const dayFmt = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' })
const whenFmt = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' })
const pctFmt = new Intl.NumberFormat('en-US', { style: 'percent', maximumFractionDigits: 0 })

const formatOptionsFor = (format: AgFormat) => {
  if (format === 'currencyFormat') return { format: usd }
  if (format === 'dateFormat') return { format: dayFmt }
  if (format === 'dateTimeFormat') return { format: whenFmt }
  if (format === 'percentageFormat') return { format: pctFmt }
  return undefined
}

// [id, name, format, hide?]
type FieldSpec = [id: string, name: string, format: AgFormat, hide?: boolean]
export const fields = (specs: FieldSpec[]): AgFieldDefinition[] =>
  specs.map(([id, name, format, hide]) => {
    const formatOptions = formatOptionsFor(format)
    return { id, name, format, ...(formatOptions && { formatOptions }), ...(hide && { hide }) }
  })

// Foreign key 'table.field' -> primary key 'table.field'.
const manyToOne = (id: string, source: string, target: string): AgRelationDefinition => {
  const [sourceTable, sourceField] = source.split('.')
  const [targetTable, targetField] = target.split('.')
  return { id, source: { tableId: sourceTable, fieldId: sourceField }, target: { tableId: targetTable, fieldId: targetField }, type: 'many-to-one' }
}

const onCalendar = (tableId: string, fieldId: string, truncate?: 'day'): AgRelationDefinition => ({
  id: `${tableId}-${fieldId}-calendar`,
  source: { tableId, fieldId },
  target: { calendarId: CALENDAR_ID },
  ...(truncate && { truncate }),
})

export const sum = (id: string) => ({ id, aggregation: 'sum' as const })
const avg = (id: string) => ({ id, aggregation: 'avg' as const })
export const countd = (id: string) => ({ id, aggregation: 'countd' as const })

const ratio = (id: string, name: string, description: string, numerator: string, denominator: string): AgExpressionFieldDefinition => ({
  id,
  name,
  description,
  format: 'percentageFormat',
  formatOptions: { format: pctFmt },
  isMeasure: true,
  expression: { operator: 'divide', inputs: [sum(numerator), sum(denominator)] },
})

/** The PayPal tables as Studio sources, to be merged into the purchase ledger's definition. */
export function paypalSources(data: PaypalTables): Required<Pick<AgDataSourcesDefinition, 'sources' | 'relationships' | 'calendars' | 'expressions'>> {
  const ymd = (v: unknown) => (typeof v === 'string' ? v.slice(0, 10) : null)
  const dates = [...data.invoices.map((r) => ymd(r.invoiceDate)), ...data.invoicePayments.map((r) => ymd(r.date)), ...data.transactions.map((r) => ymd(r.date))]
    .filter((d): d is string => !!d)
    .sort()
  const today = data.asOf.slice(0, 10)

  return {
    sources: [
      {
        id: 'customers',
        name: 'PayPal Customers',
        description: 'PayPal sandbox invoice recipients, keyed by lower-cased email.',
        data: data.customers,
        fields: fields([
          ['id', 'Customer ID', 'textFormat', true],
          ['name', 'Customer', 'textFormat'],
          ['company', 'Company', 'textFormat'],
          ['email', 'Email', 'textFormat'],
        ]),
      },
      {
        id: 'invoices',
        name: 'PayPal Invoices',
        description:
          'One row per PayPal invoice the merchant account sent (not the purchases the agent made). Issued amount excludes drafts, scheduled and cancelled invoices. Outstanding and aging apply only to open or partially paid invoices.',
        data: data.invoices,
        fields: fields([
          ['id', 'Invoice ID', 'textFormat', true],
          ['number', 'Invoice', 'textFormat'],
          ['customerId', 'Customer ID', 'textFormat', true],
          ['status', 'Invoice Status', 'textFormat'],
          ['statusGroup', 'Status Group', 'textFormat'],
          ['currency', 'Currency', 'textFormat'],
          ['paymentTerm', 'Payment Term', 'textFormat'],
          ['invoiceDate', 'Invoice Date', 'dateFormat'],
          ['dueDate', 'Due Date', 'dateFormat'],
          ['total', 'Invoice Total', 'currencyFormat'],
          ['issuedAmount', 'Invoiced', 'currencyFormat'],
          ['paidAmount', 'Paid', 'currencyFormat'],
          ['refundedAmount', 'Refunded', 'currencyFormat'],
          ['netCollected', 'Net Collected', 'currencyFormat'],
          ['isReceivable', 'Is Receivable', 'booleanFormat'],
          ['outstanding', 'Outstanding', 'currencyFormat'],
          ['overdueAmount', 'Overdue', 'currencyFormat'],
          ['daysOverdue', 'Days Overdue', 'integerFormat'],
          ['agingBucket', 'Aging Bucket', 'textFormat'],
          ['daysToPay', 'Days to Pay', 'integerFormat'],
          ['taxTotal', 'Tax', 'currencyFormat'],
        ]),
      },
      {
        id: 'invoiceItems',
        name: 'Invoice Line Items',
        description: 'Invoice lines. Line total is after line discount and tax, before invoice-level discount and shipping.',
        data: data.invoiceItems,
        fields: fields([
          ['id', 'Line ID', 'textFormat', true],
          ['invoiceId', 'Invoice ID', 'textFormat', true],
          ['name', 'Item', 'textFormat'],
          ['unit', 'Unit', 'textFormat'],
          ['quantity', 'Quantity', 'decimalFormat'],
          ['unitPrice', 'Unit Price', 'currencyFormat'],
          ['gross', 'Gross', 'currencyFormat'],
          ['discount', 'Line Discount', 'currencyFormat'],
          ['tax', 'Line Tax', 'currencyFormat'],
          ['lineTotal', 'Line Total', 'currencyFormat'],
        ]),
      },
      {
        id: 'invoicePayments',
        name: 'Invoice Payments',
        description: 'Payments and refunds recorded against invoices. Signed amount is negative for refunds; sum it for net cash.',
        data: data.invoicePayments,
        fields: fields([
          ['id', 'Payment ID', 'textFormat', true],
          ['invoiceId', 'Invoice ID', 'textFormat', true],
          ['kind', 'Payment Kind', 'textFormat'],
          ['method', 'Payment Method', 'textFormat'],
          ['date', 'Payment Date', 'dateFormat'],
          ['amount', 'Payment Amount', 'currencyFormat'],
          ['signedAmount', 'Net Cash', 'currencyFormat'],
        ]),
      },
      {
        id: 'products',
        name: 'PayPal Products',
        description: 'Catalog products sold as subscriptions.',
        data: data.products,
        fields: fields([
          ['id', 'Product ID', 'textFormat', true],
          ['name', 'Product', 'textFormat'],
          ['type', 'Product Type', 'textFormat'],
          ['category', 'Product Category', 'textFormat'],
          ['description', 'Product Description', 'textFormat'],
        ]),
      },
      {
        id: 'plans',
        name: 'Billing Plans',
        description: 'Subscription billing plans, in USD. Monthly price normalises weekly, quarterly and annual pricing to one month.',
        data: data.plans,
        fields: fields([
          ['id', 'Plan ID', 'textFormat', true],
          ['productId', 'Product ID', 'textFormat', true],
          ['name', 'Plan', 'textFormat'],
          ['status', 'Plan Status', 'textFormat'],
          ['billingInterval', 'Billed', 'textFormat'],
          ['price', 'Price', 'currencyFormat'],
          ['monthlyPrice', 'Monthly Price', 'currencyFormat'],
          ['trialDays', 'Trial Days', 'integerFormat'],
          ['setupFee', 'Setup Fee', 'currencyFormat'],
        ]),
      },
      {
        id: TXN,
        name: 'PayPal Transactions',
        description:
          'The PayPal account ledger from Transaction Search, last 31 days (not the agent purchase lineages in "Transactions"). Amounts are signed (debits negative); net is amount plus fee.',
        data: data.transactions,
        fields: fields([
          ['id', 'Transaction ID', 'textFormat'],
          ['date', 'Transaction Date', 'dateTimeFormat'],
          ['eventType', 'Event Type', 'textFormat'],
          ['status', 'Transaction Status', 'textFormat'],
          ['direction', 'Direction', 'textFormat'],
          ['currency', 'Transaction Currency', 'textFormat', true],
          ['amount', 'Transaction Amount', 'currencyFormat'],
          ['fee', 'Transaction Fee', 'currencyFormat'],
          ['net', 'Transaction Net', 'currencyFormat'],
          ['endingBalance', 'Ending Balance', 'currencyFormat'],
          ['counterparty', 'Counterparty', 'textFormat'],
          ['note', 'Transaction Note', 'textFormat'],
        ]),
      },
      {
        id: 'payouts',
        name: 'PayPal Payouts',
        description: 'Individual payouts sent from the PayPal account, as positive USD amounts, grouped into campaigns.',
        data: data.payouts,
        fields: fields([
          ['id', 'Payout ID', 'textFormat', true],
          ['campaign', 'Campaign', 'textFormat'],
          ['recipient', 'Recipient', 'textFormat'],
          ['date', 'Payout Date', 'dateTimeFormat'],
          ['status', 'Payout Status', 'textFormat'],
          ['amount', 'Payout Amount', 'currencyFormat'],
          ['fee', 'Payout Fee', 'currencyFormat'],
          ['note', 'Payout Note', 'textFormat'],
        ]),
      },
      {
        id: 'balances',
        name: 'PayPal Balances',
        description: 'Current PayPal account balance per currency.',
        data: data.balances,
        fields: fields([
          ['currency', 'Balance Currency', 'textFormat'],
          ['total', 'Total Balance', 'currencyFormat'],
          ['available', 'Available Balance', 'currencyFormat'],
          ['withheld', 'Withheld Balance', 'currencyFormat'],
        ]),
      },
    ],
    relationships: [
      manyToOne('invoice-customer', 'invoices.customerId', 'customers.id'),
      manyToOne('item-invoice', 'invoiceItems.invoiceId', 'invoices.id'),
      manyToOne('payment-invoice', 'invoicePayments.invoiceId', 'invoices.id'),
      manyToOne('plan-product', 'plans.productId', 'products.id'),
      manyToOne('purchase-paypal-transaction', 'transactions.capture_id', `${TXN}.id`),
      onCalendar('invoices', 'invoiceDate'),
      onCalendar('invoicePayments', 'date'),
      onCalendar(TXN, 'date', 'day'),
      onCalendar('payouts', 'date', 'day'),
    ],
    calendars: [
      {
        id: CALENDAR_ID,
        label: 'Calendar',
        range: { from: { type: 'date', value: dates[0] ?? today }, to: { type: 'date', value: dates.at(-1) ?? today } },
        fragments: ['year', 'quarter', 'month', 'week', 'day', 'dayOfWeek'],
      },
    ],
    expressions: [
      ratio('collectionRate', 'Collection Rate', 'Paid / invoiced. Filter to one currency first.', 'invoices.paidAmount', 'invoices.issuedAmount'),
      ratio('overdueShare', 'Overdue Share', 'Share of outstanding receivables that is past due.', 'invoices.overdueAmount', 'invoices.outstanding'),
      ratio('refundRate', 'Refund Rate', 'Refunded / paid.', 'invoices.refundedAmount', 'invoices.paidAmount'),
    ],
  }
}

// --- Pages --------------------------------------------------------------------------------------

// Position on the canvas grid, in tracks: 24 columns wide.
export const at = (xTrack: number, yTrack: number, xSpan: number, ySpan: number): AgWidgetLayoutState => ({ xTrack, yTrack, xSpan, ySpan })
export const title = (text: string) => ({ title: { enabled: true, text } })
const FONT = 'Inter, ui-sans-serif, system-ui, sans-serif'
const typography = (fontSize: number, fontWeight: 'normal' | 'bold' = 'normal') => ({ fontFamily: FONT, fontSize, fontWeight, fontStyle: 'normal' as const })

// A KPI tile: bold title, large value, optional sparkline along `sparklineX`.
export const kpi = (text: string, value: { id: string; aggregation?: 'sum' | 'avg' | 'countd' }, sparklineX?: string) => ({
  type: 'value' as const,
  dataMapping: { value: [value], ...(sparklineX && { sparklineX: [{ id: sparklineX }] }) },
  format: {
    title: { enabled: true, text, typography: typography(14, 'bold') },
    caption: { enabled: true, text: '', typography: typography(0) },
    style: { typography: typography(22) },
  },
})

const revenue: AgPageState = {
  id: 'revenue',
  widgets: {
    currency: {
      type: 'button-filter',
      dataMapping: { value: [{ id: 'invoices.currency' }] },
      format: { ...title('Currency'), style: { selection: { type: 'single' }, dimensions: { height: 28, minWidth: 48 } } },
    },
    'invoice-date': {
      type: 'date-filter',
      dataMapping: { value: [{ id: 'invoices.invoiceDate' }] },
      // No default period: a relative date filter in saved state fails to apply on load in Studio 3.0.
      format: { style: { filterType: 'relative' } },
    },
    'kpi-invoiced': kpi('Invoiced', sum('invoices.issuedAmount'), 'calendar::month'),
    'kpi-collected': kpi('Collected', sum('invoices.paidAmount'), 'calendar::month'),
    'kpi-outstanding': kpi('Outstanding', sum('invoices.outstanding'), 'invoices.outstanding'),
    'kpi-overdue': kpi('Overdue', sum('invoices.overdueAmount'), 'invoices.overdueAmount'),
    'billed-vs-collected': {
      type: 'combo-chart-grouped-column-line',
      dataMapping: {
        categoryKey: [{ id: 'calendar::month' }],
        valueKey: [sum('invoices.issuedAmount'), sum('invoices.paidAmount')],
        secondaryValueKey: [{ id: 'collectionRate' }],
      },
      format: { ...title('Invoiced and paid by invoice month, with collection rate'), style: { theme: { common: { legend: { enabled: true } } } } },
    },
    'collection-rate': {
      type: 'radial-gauge',
      dataMapping: { value: [{ id: 'collectionRate' }] },
      format: {
        ...title('Collection rate'),
        style: {
          scaleLabel: { min: 0, max: 1 },
          label: { typography: typography(24, 'bold') },
          secondaryLabel: { enabled: true, text: 'of invoiced value paid', typography: typography(12) },
        },
      },
    },
    'status-sunburst': {
      type: 'sunburst-chart',
      dataMapping: { categoryKey: [{ id: 'invoices.statusGroup' }, { id: 'customers.company' }], valueKey: [sum('invoices.total')] },
      format: title('Invoice value by status and customer'),
    },
    'items-treemap': {
      type: 'treemap-chart',
      dataMapping: { categoryKey: [{ id: 'invoiceItems.unit' }, { id: 'invoiceItems.name' }], valueKey: [sum('invoiceItems.lineTotal')] },
      format: title('Billing by unit'),
    },
    'payment-methods': {
      type: 'nightingale-chart',
      dataMapping: { categoryKey: [{ id: 'invoicePayments.method' }], valueKey: [sum('invoicePayments.amount')] },
      format: { ...title('Payments by method'), style: { theme: { nightingale: { series: { label: { enabled: true, ...typography(2) } } } } } },
    },
    'invoice-status-pivot': {
      type: 'pivot-grid',
      dataMapping: {
        rows: [{ id: 'customers.company' }, { id: 'invoices.number' }],
        columns: [{ id: 'invoices.statusGroup' }],
        values: [sum('invoices.total')],
      },
      format: {
        ...title('Invoices by customer and status (click any invoice row for details)'),
        style: { totalColumns: true, totalColumnsPlacement: 'before', grandTotalRow: { enabled: true } },
      },
    },
  },
  widgetLayout: {
    'kpi-invoiced': at(0, 0, 4, 7),
    'kpi-collected': at(4, 0, 4, 7),
    'kpi-outstanding': at(8, 0, 4, 7),
    'kpi-overdue': at(12, 0, 4, 7),
    currency: at(16, 0, 4, 7),
    'invoice-date': at(20, 0, 4, 7),
    'billed-vs-collected': at(0, 7, 16, 16),
    'collection-rate': at(16, 7, 8, 16),
    'status-sunburst': at(0, 23, 8, 18),
    'items-treemap': at(8, 23, 8, 18),
    'payment-methods': at(16, 23, 8, 18),
    'invoice-status-pivot': at(0, 41, 24, 22),
  },
  filter: {
    page: [{ field: { id: 'invoices.currency' }, model: { operator: 'isIn', value: ['USD'] }, filterWidgetId: 'currency' }],
  },
}

const receivables: AgPageState = {
  id: 'receivables',
  widgets: {
    // Invoice money isn't converted between currencies, so this page is driven by a single-select currency switch.
    currency: {
      type: 'button-filter',
      dataMapping: { value: [{ id: 'invoices.currency' }] },
      format: { ...title('Currency'), style: { selection: { type: 'single' }, dimensions: { height: 28, minWidth: 48 } } },
    },
    'kpi-outstanding': kpi('Outstanding', sum('invoices.outstanding')),
    'kpi-overdue': kpi('Overdue', sum('invoices.overdueAmount')),
    'kpi-open': kpi('Open invoices', countd('invoices.id')),
    'overdue-share': {
      type: 'radial-gauge',
      dataMapping: { value: [{ id: 'overdueShare' }] },
      format: {
        ...title('Overdue share'),
        style: {
          label: { typography: typography(24) },
          secondaryLabel: { enabled: true, text: 'of receivables past due' },
          scaleLabel: { min: 0, max: 1, typography: typography(11) },
        },
      },
    },
    aging: {
      type: 'column-chart-stacked',
      dataMapping: { categoryKey: [{ id: 'customers.name' }], valueKey: [sum('invoices.total')], legendKey: [{ id: 'invoices.status' }] },
      format: { ...title('Receivables aging by customer'), style: { theme: { common: { legend: { enabled: true } } } } },
    },
    'open-invoices': {
      type: 'grid',
      dataMapping: {
        cols: [
          { id: 'invoices.number' },
          { id: 'customers.name' },
          { id: 'customers.company' },
          { id: 'invoices.statusGroup' },
          { id: 'invoices.dueDate' },
          { id: 'invoices.daysOverdue' },
          sum('invoices.total'),
          sum('invoices.paidAmount'),
          sum('invoices.outstanding'),
        ],
      },
      sort: [{ field: { id: 'invoices.daysOverdue' }, direction: 'desc' }],
      format: title('Open invoices, most overdue first'),
    },
  },
  widgetLayout: {
    'kpi-outstanding': at(0, 0, 6, 7),
    'kpi-overdue': at(6, 0, 6, 7),
    'kpi-open': at(12, 0, 6, 7),
    currency: at(18, 0, 6, 7),
    aging: at(0, 7, 16, 18),
    'overdue-share': at(16, 7, 8, 18),
    'open-invoices': at(0, 25, 24, 20),
  },
  filter: {
    page: [
      { field: { id: 'invoices.currency' }, model: { operator: 'isIn', value: ['USD'] }, filterWidgetId: 'currency' },
      { field: { id: 'invoices.isReceivable' }, model: { operator: 'isTrue' } },
    ],
  },
}

const cash: AgPageState = {
  id: 'cash',
  widgets: {
    'kpi-balance': kpi('Available balance', sum('balances.available')),
    'kpi-paid-out': kpi('Paid out (31 days)', sum('payouts.amount')),
    'kpi-fees': kpi('Payout fees', sum('payouts.fee')),
    'kpi-recipients': kpi('Recipients', countd('payouts.recipient')),
    'payout-treemap': {
      type: 'treemap-chart',
      // Payouts aren't related to customers, so recipient (not company) is the second level.
      dataMapping: { categoryKey: [{ id: 'payouts.campaign' }, { id: 'payouts.recipient' }], valueKey: [sum('payouts.amount')] },
      format: title('Payouts by campaign and recipient'),
    },
    'campaign-donut': {
      type: 'donut-chart',
      dataMapping: { categoryKey: [{ id: 'payouts.campaign' }], valueKey: [sum('payouts.amount')] },
      format: { ...title('Payout share by campaign'), style: { custom: { pieDataLabel: { enabled: true }, totalLabel: { enabled: true } } } },
    },
    ledger: {
      type: 'grid',
      dataMapping: {
        cols: [
          { id: `${TXN}.date` },
          { id: `${TXN}.id` },
          { id: `${TXN}.eventType` },
          { id: `${TXN}.status` },
          { id: `${TXN}.counterparty` },
          { id: `${TXN}.note` },
          sum(`${TXN}.amount`),
          sum(`${TXN}.fee`),
          sum(`${TXN}.net`),
        ],
      },
      sort: [{ field: { id: `${TXN}.date` }, direction: 'desc' }],
      format: title('PayPal account ledger (click a row for transaction & linked purchase details)'),
    },
  },
  widgetLayout: {
    'kpi-balance': at(0, 0, 6, 7),
    'kpi-paid-out': at(6, 0, 6, 7),
    'kpi-fees': at(12, 0, 6, 7),
    'kpi-recipients': at(18, 0, 6, 7),
    'payout-treemap': at(0, 7, 15, 18),
    'campaign-donut': at(15, 7, 9, 18),
    ledger: at(0, 25, 24, 30),
  },
}

const catalogue: AgPageState = {
  id: 'catalogue',
  widgets: {
    'kpi-products': kpi('Products', countd('products.id')),
    'kpi-plans': kpi('Billing plans', countd('plans.id')),
    'kpi-monthly': kpi('Avg monthly price', avg('plans.monthlyPrice')),
    'kpi-trial': kpi('Avg trial days', avg('plans.trialDays')),
    'catalogue-sunburst': {
      type: 'sunburst-chart',
      dataMapping: { categoryKey: [{ id: 'products.type' }, { id: 'products.name' }, { id: 'plans.name' }], valueKey: [sum('plans.monthlyPrice')] },
      format: title('Catalogue hierarchy (by monthly price)'),
    },
    'price-range': {
      type: 'bar-chart-grouped',
      dataMapping: {
        categoryKey: [{ id: 'products.name' }],
        valueKey: [{ id: 'plans.monthlyPrice', aggregation: 'min' }, avg('plans.monthlyPrice'), { id: 'plans.monthlyPrice', aggregation: 'max' }],
      },
      format: { ...title('Monthly price range by product'), style: { theme: { common: { legend: { enabled: true, position: 'bottom' } } } } },
    },
    'plan-intervals': {
      type: 'donut-chart',
      dataMapping: { categoryKey: [{ id: 'plans.billingInterval' }], valueKey: [countd('plans.id')] },
      format: { ...title('Plans by billing interval'), style: { custom: { pieDataLabel: { enabled: true }, totalLabel: { enabled: false } } } },
    },
    plans: {
      type: 'grid',
      dataMapping: {
        cols: [
          { id: 'products.name' },
          { id: 'plans.name' },
          { id: 'plans.status' },
          { id: 'plans.billingInterval' },
          sum('plans.price'),
          sum('plans.monthlyPrice'),
          sum('plans.trialDays'),
          sum('plans.setupFee'),
        ],
      },
      sort: [{ field: sum('plans.monthlyPrice'), direction: 'desc' }],
      format: title('Plan catalogue'),
    },
  },
  widgetLayout: {
    'kpi-products': at(0, 0, 6, 7),
    'kpi-plans': at(6, 0, 6, 7),
    'kpi-monthly': at(12, 0, 6, 7),
    'kpi-trial': at(18, 0, 6, 7),
    'catalogue-sunburst': at(0, 7, 10, 20),
    'price-range': at(10, 7, 8, 20),
    'plan-intervals': at(18, 7, 6, 20),
    plans: at(0, 27, 24, 22),
  },
}

export const paypalPages: AgPageState[] = [revenue, receivables, cash, catalogue]
