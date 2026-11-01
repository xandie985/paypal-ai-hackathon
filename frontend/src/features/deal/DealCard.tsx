import { useState } from 'react'
import type { Item } from '../../api/client'
import { money, pct, short } from '../../lib/format'
import { RetryButton } from '../attack/Actions'
import { RouteCard } from '../firewall/FirewallDrawer'
import { PayPalApprove } from '../settle/PayPalApprove'

const status: Record<string, string> = {
  settled: 'bg-emerald-100 text-emerald-800',
  awaiting_approval: 'bg-amber-100 text-amber-800',
  authorized: 'bg-sky-100 text-sky-800',
  blocked: 'bg-rose-100 text-rose-800',
  rejected: 'bg-slate-200 text-slate-700',
}

const Stat = ({ k, v, sub }: { k: string; v: string; sub?: string }) => (
  <div>
    <div className="text-xs text-slate-500">{k}</div>
    <div className="font-semibold tabular-nums">{v}</div>
    {sub && <div className="text-xs text-slate-500">{sub}</div>}
  </div>
)

export function DealCard({ item, runId, busy, onApprove, onReject, onPay }: { item: Item; runId: string; busy: boolean; onApprove: () => void; onReject: () => void; onPay: () => void }) {
  const [open, setOpen] = useState(false)
  const o = item.offer
  const savePct = item.baseline ? ((Number(item.baseline) - Number(o.unit_price)) / Number(item.baseline)) * 100 : null
  const pu = item.purchase_unit
  return (
    <article className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="font-semibold">{item.title}</h3>
          <p className="text-xs text-slate-500">
            {item.method === 'negotiate' ? 'Negotiated with 4 sellers' : 'Direct buy from Channel3 listing'} · lineage <span className="font-mono">…{item.lineage_id.slice(-10)}</span>
          </p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-medium ${status[item.status] ?? 'bg-slate-100'}`}>{item.status.replace('_', ' ')}</span>
      </header>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <Stat k="Seller" v={o.seller_id} />
        <Stat k="Unit price" v={money(o.unit_price)} sub={`× ${o.quantity}`} />
        <Stat k="Total" v={money(item.total)} />
        <Stat k="Saving vs baseline" v={item.saving ? money(item.saving) : '—'} sub={pct(savePct)} />
        <Stat k="Returns / ships" v={item.return_days == null ? 'hidden' : `${item.return_days}d`} sub={`ships in ${o.ship_days}d`} />
      </div>
      {o.terms && <p className="rounded bg-slate-50 p-2 text-xs text-slate-600">Seller terms: {o.terms}</p>}
      <RouteCard item={item} busy={busy} onApprove={onApprove} onReject={onReject} />
      <div className="flex flex-wrap items-center gap-3">
        <PayPalApprove item={item} busy={busy} onPay={onPay} />
        <RetryButton runId={runId} item={item} />
        {item.seal && (
          <button className="text-xs text-indigo-700 hover:underline" onClick={() => setOpen(!open)}>
            {open ? 'Hide' : 'Show'} PayPal order &amp; seal
          </button>
        )}
      </div>
      {open && item.seal && pu && (
        <div className="grid gap-3 rounded border border-slate-200 p-3 text-xs sm:grid-cols-2">
          <div>
            <div className="mb-1 font-semibold">PayPal Orders v2 purchase unit</div>
            <table className="w-full">
              <tbody>
                {pu.items?.map((it) => (
                  <tr key={it.sku}><td>{it.name}</td><td className="text-right">{it.quantity} × {money(it.unit_amount.value)}</td></tr>
                ))}
                {Object.entries(pu.amount.breakdown ?? {}).map(([k, v]) => (
                  <tr key={k} className="text-slate-500"><td>{k.replace('_', ' ')}</td><td className="text-right">{money(v.value)}</td></tr>
                ))}
                <tr className="border-t font-semibold"><td>Amount</td><td className="text-right">{money(pu.amount.value)} {pu.amount.currency_code}</td></tr>
              </tbody>
            </table>
            <p className="mt-1 text-slate-500">custom_id carries the lineage: <span className="font-mono">{pu.custom_id.slice(-14)}</span></p>
          </div>
          <div className="space-y-0.5">
            <div className="mb-1 font-semibold">Decide-and-prove seal</div>
            <div>order <b>{item.seal.order_id}</b> ({item.order_status})</div>
            <div>terms hash <span className="font-mono">{short(item.seal.terms_hash, 14)}</span></div>
            <div>decision digest <span className="font-mono">{short(item.seal.decision_digest, 14)}</span></div>
            <div>buyer IP <span className="font-mono">{item.seal.buyer_ip}</span></div>
            {item.capture_id && <div>capture <b>{item.capture_id}</b></div>}
          </div>
        </div>
      )}
    </article>
  )
}
