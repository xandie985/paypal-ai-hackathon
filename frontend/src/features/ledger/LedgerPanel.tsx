import { useEffect, useState } from 'react'
import { api, type LedgerView } from '../../api/client'
import { short } from '../../lib/format'

export function LedgerPanel({ runId, entries }: { runId: string; entries: number }) {
  const [view, setView] = useState<LedgerView | null>(null)
  useEffect(() => {
    api.ledger(runId).then(setView).catch(() => setView(null))
  }, [runId, entries])
  if (!view) return null
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Evidence ledger <span className="text-xs font-normal text-slate-500">hash-chained, append-only</span></h2>
        <span className={`rounded-full px-3 py-1 text-xs font-medium ${view.chain_ok ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'}`}>
          {view.chain_ok ? `chain verified · ${view.entries.length} entries` : `broken at #${view.first_bad_seq}`}
        </span>
      </div>
      <div className="mt-2 max-h-72 overflow-auto">
        <table className="w-full text-left font-mono text-xs">
          <thead className="sticky top-0 bg-white text-slate-500"><tr><th>#</th><th>stage</th><th>kind</th><th>lineage</th><th>prev</th><th>hash</th></tr></thead>
          <tbody>
            {view.entries.map((e) => (
              <tr key={e.seq} className="border-t border-slate-100">
                <td>{e.seq}</td><td>{e.stage}</td><td className="font-semibold">{e.kind}</td><td>…{e.lineage_id.slice(-6)}</td><td className="text-slate-400">{short(e.prev_hash, 6)}</td><td>{short(e.entry_hash, 10)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
