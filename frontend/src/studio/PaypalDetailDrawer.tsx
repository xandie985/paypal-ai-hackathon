import type { PaypalTables, StudioRow } from '../api/client'

export type PaypalSelection =
  | { kind: 'invoice'; id: string } // invoice number, e.g. PG-1001
  | { kind: 'transaction'; id: string } // transaction_id / capture_id, e.g. CAP-000064 or TXN-FIXT-0001

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
const eur = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'EUR' })
const fmtMoney = (v: unknown, currency = 'USD') => {
  if (v == null || v === '') return '—'
  const n = Number(v)
  if (Number.isNaN(n)) return String(v)
  return (currency === 'EUR' ? eur : usd).format(n)
}
const dayFmt = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' })
const whenFmt = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' })
const fmtDate = (v: unknown, withTime = false) => {
  if (!v || typeof v !== 'string') return '—'
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? v : (withTime ? whenFmt : dayFmt).format(d)
}

export function PaypalDetailDrawer({
  selection,
  paypal,
  rows,
  onClose,
  onOpenLineage,
}: {
  selection: PaypalSelection
  paypal: PaypalTables
  rows: StudioRow[]
  onClose: () => void
  onOpenLineage: (lineageId: string) => void
}) {
  if (selection.kind === 'invoice') {
    const inv = paypal.invoices.find((i) => String(i.number) === selection.id || String(i.id) === selection.id)
    if (!inv) return null
    const currency = String(inv.currency ?? 'USD')
    const customer = paypal.customers.find((c) => c.id === inv.customerId)
    const items = paypal.invoiceItems.filter((it) => it.invoiceId === inv.id)
    const payments = paypal.invoicePayments.filter((p) => p.invoiceId === inv.id)

    return (
      <aside
        className="absolute inset-y-0 right-0 z-20 flex w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-xl"
        aria-label="PayPal invoice detail"
      >
        <header className="flex items-start justify-between border-b border-slate-200 p-4">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="font-semibold">Invoice {String(inv.number)}</h2>
              <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700">
                {String(inv.status ?? inv.statusGroup)}
              </span>
              <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-600">{currency}</span>
            </div>
            <p className="mt-0.5 font-mono text-xs text-slate-500">{String(inv.id)}</p>
          </div>
          <button onClick={onClose} className="rounded px-2 py-1 text-slate-500 hover:bg-slate-100" aria-label="Close invoice detail">
            ✕
          </button>
        </header>

        <div className="min-h-0 flex-1 space-y-4 overflow-auto p-4 text-xs">
          {customer && (
            <section className="rounded border border-slate-200 bg-slate-50 p-3">
              <h3 className="font-semibold text-slate-700">Customer</h3>
              <p className="mt-1 font-medium text-slate-900">{String(customer.name)}</p>
              <p className="text-slate-600">
                {String(customer.company)} · <span className="font-mono">{String(customer.email ?? '—')}</span>
              </p>
            </section>
          )}

          <section className="grid grid-cols-2 gap-2 rounded border border-slate-200 p-3">
            <div>
              <span className="text-slate-500">Invoice date</span>
              <p className="font-medium">{fmtDate(inv.invoiceDate)}</p>
            </div>
            <div>
              <span className="text-slate-500">Due date</span>
              <p className="font-medium">{fmtDate(inv.dueDate)}</p>
            </div>
            <div>
              <span className="text-slate-500">Total</span>
              <p className="font-semibold text-slate-900">{fmtMoney(inv.total, currency)}</p>
            </div>
            <div>
              <span className="text-slate-500">Paid / Net collected</span>
              <p className="font-semibold text-emerald-700">{fmtMoney(inv.netCollected, currency)}</p>
            </div>
            <div>
              <span className="text-slate-500">Outstanding</span>
              <p className="font-semibold text-amber-700">{fmtMoney(inv.outstanding, currency)}</p>
            </div>
            <div>
              <span className="text-slate-500">Aging</span>
              <p className="font-medium">
                {inv.isReceivable ? `${String(inv.agingBucket ?? 'Current')} (${Number(inv.daysOverdue ?? 0)}d overdue)` : 'Closed'}
              </p>
            </div>
          </section>

          <section className="space-y-1.5">
            <h3 className="font-semibold text-slate-700">Line items ({items.length})</h3>
            <div className="divide-y divide-slate-100 rounded border border-slate-200">
              {items.map((it) => (
                <div key={String(it.id)} className="flex items-center justify-between p-2">
                  <div>
                    <p className="font-medium text-slate-900">{String(it.name)}</p>
                    <p className="text-slate-500">
                      {String(it.quantity)} × {fmtMoney(it.unitPrice, currency)}
                    </p>
                  </div>
                  <span className="font-semibold">{fmtMoney(it.lineTotal, currency)}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="space-y-1.5">
            <h3 className="font-semibold text-slate-700">Payments & refunds ({payments.length})</h3>
            {payments.length === 0 ? (
              <p className="text-slate-500">No payments recorded yet.</p>
            ) : (
              <div className="divide-y divide-slate-100 rounded border border-slate-200">
                {payments.map((p) => (
                  <div key={String(p.id)} className="flex items-center justify-between p-2">
                    <div>
                      <span
                        className={`rounded px-1.5 py-0.5 font-medium ${p.kind === 'Refund' ? 'bg-rose-100 text-rose-800' : 'bg-emerald-100 text-emerald-800'}`}
                      >
                        {String(p.kind)}
                      </span>{' '}
                      <span className="text-slate-600">{String(p.method)}</span>
                      <p className="mt-0.5 text-slate-400">{fmtDate(p.date)}</p>
                    </div>
                    <span className={`font-semibold ${Number(p.signedAmount) < 0 ? 'text-rose-700' : 'text-emerald-700'}`}>
                      {fmtMoney(p.signedAmount, currency)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </aside>
    )
  }

  const txn = paypal.transactions.find((t) => String(t.id) === selection.id)
  const payout = paypal.payouts.find((p) => String(p.id) === selection.id)
  const purchase = rows.find((r) => r.capture_id === selection.id)
  if (!txn && !payout && !purchase) return null
  const currency = String(txn?.currency ?? 'USD')

  return (
    <aside
      className="absolute inset-y-0 right-0 z-20 flex w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-xl"
      aria-label="PayPal transaction detail"
    >
      <header className="flex items-start justify-between border-b border-slate-200 p-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-semibold">PayPal Transaction</h2>
            {txn?.eventType && (
              <span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs font-medium text-sky-800">{String(txn.eventType)}</span>
            )}
            {txn?.status && (
              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800">{String(txn.status)}</span>
            )}
          </div>
          <p className="mt-0.5 font-mono text-xs text-slate-500">{selection.id}</p>
        </div>
        <button onClick={onClose} className="rounded px-2 py-1 text-slate-500 hover:bg-slate-100" aria-label="Close transaction detail">
          ✕
        </button>
      </header>

      <div className="min-h-0 flex-1 space-y-4 overflow-auto p-4 text-xs">
        {txn ? (
          <section className="grid grid-cols-2 gap-2 rounded border border-slate-200 p-3">
            <div>
              <span className="text-slate-500">Initiated</span>
              <p className="font-medium">{fmtDate(txn.date, true)}</p>
            </div>
            <div>
              <span className="text-slate-500">Direction</span>
              <p className="font-medium">{String(txn.direction ?? '—')}</p>
            </div>
            <div>
              <span className="text-slate-500">Gross amount</span>
              <p className="font-semibold text-slate-900">{fmtMoney(txn.amount, currency)}</p>
            </div>
            <div>
              <span className="text-slate-500">PayPal fee</span>
              <p className="font-medium text-slate-700">{fmtMoney(txn.fee, currency)}</p>
            </div>
            <div>
              <span className="text-slate-500">Net impact</span>
              <p className="font-semibold text-slate-900">{fmtMoney(txn.net, currency)}</p>
            </div>
            <div>
              <span className="text-slate-500">Ending balance</span>
              <p className="font-medium">{fmtMoney(txn.endingBalance, currency)}</p>
            </div>
            <div className="col-span-2">
              <span className="text-slate-500">Counterparty</span>
              <p className="font-mono text-slate-800">{String(txn.counterparty ?? payout?.recipient ?? '—')}</p>
            </div>
            {txn.note && (
              <div className="col-span-2">
                <span className="text-slate-500">Note</span>
                <p className="text-slate-800">{String(txn.note)}</p>
              </div>
            )}
          </section>
        ) : (
          <p className="rounded border border-slate-200 bg-slate-50 p-3 text-slate-600">
            Capture <code className="font-mono">{selection.id}</code> is recorded in the agent ledger (outside the current 31-day Transaction Search fixture window).
          </p>
        )}

        {payout && (
          <section className="rounded border border-slate-200 bg-slate-50 p-3">
            <h3 className="font-semibold text-slate-700">Payout campaign</h3>
            <p className="mt-1">
              Campaign: <span className="font-semibold">{String(payout.campaign)}</span> · Recipient:{' '}
              <span className="font-mono">{String(payout.recipient)}</span>
            </p>
          </section>
        )}

        {purchase && (
          <section className="space-y-2 rounded border border-indigo-200 bg-indigo-50/60 p-3">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-indigo-950">Linked Agent Purchase</h3>
              <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[11px] font-medium text-indigo-800">
                {purchase.route}
              </span>
            </div>
            <p className="text-slate-700">
              The autonomous agent settled this payment after firewall check ({purchase.firewall_ms ?? 0} ms).
            </p>
            <div className="grid grid-cols-2 gap-1.5 text-slate-700">
              <div>
                <span className="text-slate-500">Vendor:</span> <span className="font-medium">{purchase.vendor}</span>
              </div>
              <div>
                <span className="text-slate-500">Category:</span> <span className="font-medium">{purchase.category}</span>
              </div>
              <div>
                <span className="text-slate-500">Order ID:</span> <span className="font-mono">{purchase.order_id}</span>
              </div>
              <div>
                <span className="text-slate-500">Saved vs retail:</span>{' '}
                <span className="font-medium text-emerald-700">{fmtMoney(purchase.savings)}</span>
              </div>
            </div>
            <button
              onClick={() => onOpenLineage(purchase.lineage_id)}
              className="mt-1 w-full rounded bg-indigo-600 px-3 py-1.5 text-center font-medium text-white hover:bg-indigo-700"
            >
              Trace sealed lineage ({purchase.lineage_id}) →
            </button>
          </section>
        )}
      </div>
    </aside>
  )
}
