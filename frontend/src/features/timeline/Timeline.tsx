import { useEffect, useRef } from 'react'
import type { RunEvent } from '../../api/client'

const STAGES: Record<string, { label: string; tone: string }> = {
  '1': { label: 'Delegate', tone: 'bg-violet-100 text-violet-800' },
  '2': { label: 'Discover', tone: 'bg-sky-100 text-sky-800' },
  '3': { label: 'Govern', tone: 'bg-amber-100 text-amber-800' },
  '4': { label: 'Settle', tone: 'bg-emerald-100 text-emerald-800' },
  '5': { label: 'Verify', tone: 'bg-teal-100 text-teal-800' },
  '6': { label: 'Reconcile', tone: 'bg-indigo-100 text-indigo-800' },
  '7': { label: 'Payout', tone: 'bg-rose-100 text-rose-800' },
  run: { label: 'Run', tone: 'bg-slate-100 text-slate-700' },
}

const words = (s: string) => s.replace(/_/g, ' ')

/**
 * Every event of the run as one vertical stream, oldest first, that keeps itself scrolled to the newest. It fills
 * whatever height its parent gives it and scrolls inside that, so it can sit beside a taller panel without stretching it.
 */
export function Timeline({ events, className = '' }: { events: RunEvent[]; className?: string }) {
  const end = useRef<HTMLLIElement>(null)
  useEffect(() => {
    end.current?.scrollIntoView({ block: 'nearest' })
  }, [events.length])
  return (
    <section className={`flex min-h-0 flex-col rounded-2xl border border-slate-200 bg-white p-4 shadow-xs ${className}`}>
      <h2 className="flex items-baseline justify-between font-semibold text-slate-900">
        Timeline <span className="text-xs font-normal text-slate-400">{events.length} events</span>
      </h2>
      {events.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">Nothing yet. Run the agent and every step lands here.</p>
      ) : (
        <ol className="mt-3 min-h-0 flex-1 space-y-2 overflow-y-auto pr-1 text-xs" aria-live="polite">
          {events.map((e) => {
            const st = STAGES[e.stage] ?? { label: e.stage, tone: 'bg-slate-100 text-slate-700' }
            return (
              <li key={e.seq} className="flex items-start gap-2">
                <span className="mt-0.5 w-5 shrink-0 text-right font-mono text-[10px] text-slate-400">{e.seq}</span>
                <span className={`mt-px shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${st.tone}`}>{st.label}</span>
                <span className="min-w-0 flex-1 break-words text-slate-800">
                  {words(e.event)}
                  {typeof e.lineage_id === 'string' && <span className="font-mono text-slate-400"> …{e.lineage_id.slice(-6)}</span>}
                </span>
              </li>
            )
          })}
          <li ref={end} aria-hidden="true" />
        </ol>
      )}
    </section>
  )
}
