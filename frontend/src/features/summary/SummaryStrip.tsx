import type { RunSnapshot } from '../../api/client'
import { money } from '../../lib/format'

const tile = 'rounded-lg border border-slate-200 bg-white p-3'

export function SummaryStrip({ run }: { run: RunSnapshot }) {
  const used = Math.min(100, (Number(run.spent) / Number(run.budget)) * 100)
  const saved = run.items.reduce((a, i) => a + (i.saving ? Number(i.saving) : 0), 0)
  const count = (r: string) => run.items.filter((i) => i.decision?.route === r).length
  return (
    <div className="grid gap-3 sm:grid-cols-4">
      <div className={tile}>
        <div className="text-xs text-slate-500">Budget used</div>
        <div className="text-lg font-semibold">
          {money(run.spent)} <span className="text-sm font-normal text-slate-500">of {money(run.budget)}</span>
        </div>
        <div className="mt-1 h-1.5 rounded bg-slate-100">
          <div className="h-1.5 rounded bg-indigo-500" style={{ width: `${used}%` }} />
        </div>
      </div>
      <div className={tile}>
        <div className="text-xs text-slate-500">Saved vs retail baseline</div>
        <div className="text-lg font-semibold text-emerald-700">{money(saved)}</div>
      </div>
      <div className={tile}>
        <div className="text-xs text-slate-500">Firewall routes</div>
        <div className="text-sm font-medium">
          <span className="text-emerald-700">{count('AUTO_SETTLE')} auto</span> ·{' '}
          <span className="text-amber-700">{count('HUMAN_APPROVAL')} human</span> ·{' '}
          <span className="text-rose-700">{count('BLOCKED')} blocked</span>
        </div>
      </div>
      <div className={tile}>
        <div className="text-xs text-slate-500">Sealed evidence entries</div>
        <div className="text-lg font-semibold">{run.ledger_entries}</div>
      </div>
    </div>
  )
}
