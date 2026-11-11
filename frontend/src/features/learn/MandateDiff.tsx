import { useEffect, useState } from 'react'
import { api, type Calibration, type MandateDiffRow } from '../../api/client'
import { money } from '../../lib/format'

const label: Record<string, string> = {
  auto_threshold: 'Auto-settle threshold',
  vendor_allowlist: 'Vendor allowlist',
  budget: 'Budget',
  per_txn_cap: 'Per-purchase cap',
  min_return_days: 'Min return days',
}

function Row({ d }: { d: MandateDiffRow }) {
  const num = d.field === 'auto_threshold' || d.field === 'budget' || d.field === 'per_txn_cap'
  return (
    <div className="rounded border border-slate-200 p-2 text-sm">
      <div className="text-xs font-medium text-slate-500">{label[d.field] ?? d.field}</div>
      {d.removed || d.added ? (
        <div className="mt-1 flex flex-wrap gap-1">
          {(d.before as string[]).map((v) => (
            <span key={v} className={`rounded px-2 py-0.5 text-xs ${d.removed?.includes(v) ? 'bg-rose-100 text-rose-800 line-through' : 'bg-slate-100'}`}>{v}</span>
          ))}
          {d.added?.map((v) => <span key={v} className="rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-800">+ {v}</span>)}
        </div>
      ) : (
        <div className="mt-1 tabular-nums">
          <span className="rounded bg-rose-50 px-2 py-0.5 text-rose-800 line-through">{num ? money(d.before as string) : String(d.before)}</span>{' '}
          →{' '}
          <span className="rounded bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-800">{num ? money(d.after as string) : String(d.after)}</span>
        </div>
      )}
    </div>
  )
}

// Stage 10's output: the rules the agent ran under (v1) and the rules it earned from the outcomes (v2).
export function MandateDiff({ runId, onClose }: { runId?: string; onClose: () => void }) {
  const [items, setItems] = useState<Calibration[] | null>(null)
  const [now, setNow] = useState<string[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [idx, setIdx] = useState(0)
  useEffect(() => {
    api.studioCalibrations().then((r) => setItems(r.calibrations)).catch((e) => setError(String(e.message ?? e)))
    if (runId) api.runCalibration(runId).then((r) => setNow(r.changed ? r.changes : [])).catch(() => setNow(null))
  }, [runId])
  const c = items?.[idx]
  return (
    <aside className="absolute inset-y-0 right-0 z-20 flex w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-xl" aria-label="Mandate before and after">
      <header className="flex items-start justify-between border-b border-slate-200 p-4">
        <div>
          <h2 className="font-semibold">Mandate v1 → v2</h2>
          <p className="text-xs text-slate-500">Stage 10 turns outcomes into tighter rules. Every version links to its parent by digest.</p>
        </div>
        <button onClick={onClose} className="rounded px-2 py-1 text-slate-500 hover:bg-slate-100" aria-label="Close mandate diff">✕</button>
      </header>
      <div className="min-h-0 flex-1 space-y-3 overflow-auto p-4">
        {runId && (
          <p className="rounded bg-slate-50 p-2 text-xs text-slate-600">
            Your current run: {now == null ? '…' : now.length ? `would change — ${now.join('; ')}` : 'nothing to learn yet (no lost dispute, weak supplier, or 5+ clean approvals).'}
          </p>
        )}
        {error && <p className="text-sm text-rose-800">{error}</p>}
        {items && !items.length && <p className="text-sm text-slate-500">No calibrated mandates in the seeded history.</p>}
        {items && items.length > 1 && (
          <label className="block text-xs text-slate-500">
            Seeded mandate
            <select className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm" value={idx} onChange={(e) => setIdx(Number(e.target.value))}>
              {items.map((x, i) => <option key={x.to_lineage} value={i}>{x.before.version} → {x.after.version} · {new Date(x.created_at).toLocaleDateString()} · {x.changes.length} change(s)</option>)}
            </select>
          </label>
        )}
        {c && (
          <>
            <div className="flex items-center gap-2 text-xs">
              <span className="rounded bg-slate-100 px-2 py-0.5">v{c.before.version}</span>→<span className="rounded bg-indigo-100 px-2 py-0.5 text-indigo-800">v{c.after.version}</span>
              <span className={`rounded-full px-2 py-0.5 ${c.parent_digest_linked ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'}`}>
                {c.parent_digest_linked ? 'parent digest linked' : 'parent digest MISMATCH'}
              </span>
            </div>
            {c.diff.map((d) => <Row key={d.field} d={d} />)}
            <div>
              <div className="text-xs font-medium text-slate-500">Why</div>
              <ul className="mt-1 list-disc pl-5 text-sm">{c.changes.map((x) => <li key={x}>{x}</li>)}</ul>
            </div>
            <div>
              <div className="text-xs font-medium text-slate-500">Supplier trust behind it</div>
              <ul className="mt-1 space-y-1">
                {Object.entries(c.trust).map(([v, t]) => (
                  <li key={v} className="flex items-center gap-2 text-xs">
                    <span className="w-36 truncate">{v}</span>
                    <span className="h-1.5 flex-1 rounded bg-slate-100"><span className={`block h-1.5 rounded ${t < 0.5 ? 'bg-rose-500' : 'bg-emerald-500'}`} style={{ width: `${t * 100}%` }} /></span>
                    <span className="w-9 text-right tabular-nums">{Math.round(t * 100)}%</span>
                  </li>
                ))}
              </ul>
            </div>
          </>
        )}
      </div>
    </aside>
  )
}
