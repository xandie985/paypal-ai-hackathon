import type { Candidate, RunEvent } from '../../api/client'
import { money } from '../../lib/format'

function CandidateRow({ c, baseline }: { c: Candidate; baseline: number }) {
  const price = Number(c.price)
  const diff = ((price - baseline) / baseline) * 100
  return (
    <tr className="border-t border-slate-100 align-middle">
      <td className="py-2 pr-3">
        <div className="flex items-center gap-2">
          {c.image_url ? (
            <img src={c.image_url} alt="" className="h-9 w-9 rounded object-cover" />
          ) : (
            <div className="grid h-9 w-9 place-items-center rounded bg-slate-100 text-xs text-slate-400">img</div>
          )}
          <div>
            <div className="font-medium">{c.url ? <a className="text-indigo-700 hover:underline" href={c.url} target="_blank" rel="noreferrer">{c.title}</a> : c.title}</div>
            <div className="text-xs text-slate-500">{c.product_id}</div>
          </div>
        </div>
      </td>
      <td className="pr-3">{c.merchant}</td>
      <td className="pr-3 text-right tabular-nums">
        {money(price)}
        <div className={`text-xs ${diff <= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>{diff > 0 ? '+' : ''}{diff.toFixed(1)}% vs median</div>
      </td>
      <td className="pr-3">
        {c.return_days == null ? <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800">terms hidden</span> : `${c.return_days}d returns`}
      </td>
      <td>
        {c.allowlisted ? (
          <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-800">on allowlist</span>
        ) : (
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">not allowed</span>
        )}
      </td>
    </tr>
  )
}

export function MarketPanel({ events }: { events: RunEvent[] }) {
  const found = events.filter((e) => e.event === 'discovered')
  if (!found.length) return null
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="font-semibold">2 · Market discovery <span className="text-xs font-normal text-slate-500">Channel3 product graph</span></h2>
      {found.map((e) => {
        const cands = (e.candidates as Candidate[]) ?? []
        const sources = [...new Set(cands.map((c) => c.source))].join(', ')
        return (
          <div key={String(e.seq)} className="mt-3">
            <div className="flex flex-wrap items-baseline gap-2 text-sm">
              <b>{String(e.query)}</b>
              <span className="text-slate-500">× {String(e.quantity)}</span>
              <span className="rounded bg-indigo-50 px-2 py-0.5 text-xs text-indigo-800">baseline {money(e.baseline as string)}</span>
              <span className="text-xs text-slate-400">source: {sources || 'none'}</span>
            </div>
            <div className="overflow-x-auto">
              <table className="mt-1 w-full min-w-[34rem] text-left text-sm">
                <thead className="text-xs text-slate-500">
                  <tr><th className="font-normal">Product</th><th className="pr-3 font-normal">Merchant</th><th className="pr-3 text-right font-normal">Price</th><th className="pr-3 font-normal">Returns</th><th className="font-normal">Mandate</th></tr>
                </thead>
                <tbody>{cands.map((c) => <CandidateRow key={c.product_id} c={c} baseline={Number(e.baseline)} />)}</tbody>
              </table>
            </div>
          </div>
        )
      })}
    </section>
  )
}
