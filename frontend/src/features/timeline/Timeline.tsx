import type { RunEvent } from '../../api/client'

const STAGES: Record<string, string> = { '1': 'Delegate', '2': 'Discover', '3': 'Govern', '4': 'Settle', run: 'Run' }

export function Timeline({ events }: { events: RunEvent[] }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="font-semibold">Timeline</h2>
      <ol className="mt-2 max-h-80 space-y-1 overflow-auto font-mono text-xs">
        {events.map((e) => (
          <li key={e.seq}>
            <span className="text-slate-400">{String(e.seq).padStart(2, '0')}</span> <b>{STAGES[e.stage] ?? e.stage}</b> {e.event}
            {typeof e.lineage_id === 'string' && <span className="text-slate-400"> …{e.lineage_id.slice(-6)}</span>}
          </li>
        ))}
      </ol>
    </section>
  )
}
