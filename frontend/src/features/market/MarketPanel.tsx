import type { Candidate, RunEvent } from '../../api/client'
import { money } from '../../lib/format'

// One product as a card in a horizontal strip: image on top, then the name, merchant, price against the median, and the
// mandate's verdict as chips. Fixed width so a row of them scrolls sideways instead of squeezing.
function CandidateCard({ c, baseline }: { c: Candidate; baseline: number }) {
  const price = Number(c.price)
  const diff = baseline ? ((price - baseline) / baseline) * 100 : 0
  return (
    <li className={`flex w-56 shrink-0 snap-start flex-col overflow-hidden rounded-xl border bg-white ${c.allowlisted ? 'border-slate-200' : 'border-slate-200 opacity-70'}`}>
      {c.image_url ? (
        <img src={c.image_url} alt={c.title} loading="lazy" className="h-28 w-full border-b border-slate-100 bg-slate-50 object-contain p-2" />
      ) : (
        <div className="grid h-28 w-full place-items-center border-b border-slate-100 bg-gradient-to-br from-slate-50 to-indigo-50" aria-hidden="true">
          <span className="grid h-12 w-12 place-items-center rounded-xl bg-white text-base font-bold text-indigo-700 shadow-xs">
            {c.merchant.slice(0, 2).toUpperCase()}
          </span>
        </div>
      )}
      <div className="flex flex-1 flex-col gap-1.5 p-3">
        <div className="line-clamp-2 min-h-[2.5rem] text-sm font-semibold leading-snug text-slate-900" title={c.title}>
          {c.url ? (
            <a className="hover:text-indigo-700 hover:underline" href={c.url} target="_blank" rel="noreferrer">
              {c.title}
            </a>
          ) : (
            c.title
          )}
        </div>
        <div className="truncate text-xs text-slate-500">{c.merchant}</div>
        <div className="mt-auto flex items-baseline justify-between gap-2 pt-1">
          <span className="text-base font-bold tabular-nums text-slate-900">{money(price)}</span>
          <span className={`text-[11px] font-medium tabular-nums ${diff <= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
            {diff > 0 ? '+' : ''}
            {diff.toFixed(1)}% vs median
          </span>
        </div>
        <div className="flex flex-wrap gap-1">
          {c.return_days == null ? (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-800">return terms hidden</span>
          ) : (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-700">{c.return_days}-day returns</span>
          )}
          {c.allowlisted ? (
            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-800">on allowlist</span>
          ) : (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500">not allowed</span>
          )}
        </div>
      </div>
    </li>
  )
}

/** One row per item type the agent searched for; each row scrolls sideways through its candidates. */
export function MarketPanel({ events, className = '' }: { events: RunEvent[]; className?: string }) {
  const found = events.filter((e) => e.event === 'discovered')
  if (!found.length) return null
  return (
    <section className={`min-w-0 space-y-5 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs ${className}`}>
      <h2 className="flex flex-wrap items-baseline gap-x-2 font-semibold text-slate-900">
        2 · Market discovery <span className="text-xs font-normal text-slate-500">Channel3 product graph</span>
      </h2>
      {found.map((e) => {
        const cands = (e.candidates as Candidate[]) ?? []
        const sources = [...new Set(cands.map((c) => c.source))].join(', ')
        return (
          <div key={String(e.seq)}>
            <div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
              <b className="text-slate-900">{String(e.query)}</b>
              <span className="text-slate-500">× {String(e.quantity)}</span>
              <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-800">baseline {money(e.baseline as string)}</span>
              <span className="text-xs text-slate-400">{cands.length} found</span>
              <span className="ml-auto text-xs text-slate-400">source: {sources || 'none'}</span>
            </div>
            <ul className="-mx-1 flex snap-x gap-3 overflow-x-auto px-1 pb-2" aria-label={`${String(e.query)} candidates`}>
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
