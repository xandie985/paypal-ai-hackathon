import type { Candidate, RunEvent } from '../../api/client'
import { money } from '../../lib/format'

// One product as a card, not a table row: the panel sits in a half-width column, where a five-column table
// forced a sideways scroll. Image and name on the left, price on the right, the terms as chips underneath.
function CandidateCard({ c, baseline }: { c: Candidate; baseline: number }) {
  const price = Number(c.price)
  const diff = baseline ? ((price - baseline) / baseline) * 100 : 0
  return (
    <li className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-3">
      {c.image_url ? (
        <img src={c.image_url} alt="" className="h-14 w-14 shrink-0 rounded-lg border border-slate-100 object-cover" />
      ) : (
        <div className="grid h-14 w-14 shrink-0 place-items-center rounded-lg bg-slate-100 text-[10px] text-slate-400">no image</div>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="line-clamp-2 text-sm font-semibold leading-snug text-slate-900">
              {c.url ? (
                <a className="hover:text-indigo-700 hover:underline" href={c.url} target="_blank" rel="noreferrer">
                  {c.title}
                </a>
              ) : (
                c.title
              )}
            </div>
            <div className="mt-0.5 truncate text-xs text-slate-500">{c.merchant}</div>
          </div>
          <div className="shrink-0 text-right">
            <div className="text-sm font-bold tabular-nums text-slate-900">{money(price)}</div>
            <div className={`text-[11px] font-medium tabular-nums ${diff <= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
              {diff > 0 ? '+' : ''}
              {diff.toFixed(1)}% vs median
            </div>
          </div>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {c.return_days == null ? (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800">return terms hidden</span>
          ) : (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-700">{c.return_days}-day returns</span>
          )}
          {c.allowlisted ? (
            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800">on allowlist</span>
          ) : (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500">not allowed</span>
          )}
          <span className="truncate font-mono text-[10px] text-slate-400">{c.product_id}</span>
        </div>
      </div>
    </li>
  )
}

export function MarketPanel({ events }: { events: RunEvent[] }) {
  const found = events.filter((e) => e.event === 'discovered')
  if (!found.length) return null
  return (
    <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs">
      <h2 className="flex flex-wrap items-baseline gap-x-2 font-semibold text-slate-900">
        2 · Market discovery <span className="text-xs font-normal text-slate-500">Channel3 product graph</span>
      </h2>
      {found.map((e) => {
        const cands = (e.candidates as Candidate[]) ?? []
        const sources = [...new Set(cands.map((c) => c.source))].join(', ')
        return (
          <div key={String(e.seq)}>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-slate-100 pb-2 text-sm">
              <b className="text-slate-900">{String(e.query)}</b>
              <span className="text-slate-500">× {String(e.quantity)}</span>
              <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-800">baseline {money(e.baseline as string)}</span>
              <span className="ml-auto text-xs text-slate-400">source: {sources || 'none'}</span>
            </div>
            <ul className="mt-2 space-y-2">
              {cands.map((c) => (
                <CandidateCard key={c.product_id} c={c} baseline={Number(e.baseline)} />
              ))}
            </ul>
          </div>
        )
      })}
    </section>
  )
}
