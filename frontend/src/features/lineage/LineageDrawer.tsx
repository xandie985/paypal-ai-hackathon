import { useEffect, useState } from 'react'
import { api, type LineageView } from '../../api/client'
import { short } from '../../lib/format'

const KIND_TONE: Record<string, string> = {
  decision: 'bg-sky-100 text-sky-800',
  approval: 'bg-emerald-100 text-emerald-800',
  rejection: 'bg-slate-200 text-slate-700',
  seal: 'bg-indigo-100 text-indigo-800',
  capture: 'bg-emerald-100 text-emerald-800',
  dispute_outcome: 'bg-amber-100 text-amber-800',
}

// Mount with key={lineage}: a new purchase starts from empty state instead of resetting it in an effect.
// One purchase's sealed entries, oldest first. Each row shows the previous row's hash it commits to.
export function LineageDrawer({
  lineage,
  onClose,
  onOpenPaypalTxn,
}: {
  lineage: string
  onClose: () => void
  onOpenPaypalTxn?: (captureId: string) => void
}) {
  const [view, setView] = useState<LineageView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  useEffect(() => {
    let live = true
    api.studioLineage(lineage).then((v) => live && setView(v)).catch((e) => live && setError(String(e.message ?? e)))
    return () => {
      live = false
    }
  }, [lineage])

  const captureId = view?.entries.find((e) => e.kind === 'capture')?.payload?.capture_id as string | undefined

  return (
    <aside className="absolute inset-y-0 right-0 z-20 flex w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-xl" aria-label="Lineage timeline">
      <header className="flex items-start justify-between border-b border-slate-200 p-4">
        <div>
          <h2 className="font-semibold">Lineage timeline</h2>
          <p className="break-all font-mono text-xs text-slate-500">{lineage}</p>
          {view && (
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
              <span className={`rounded-full px-2 py-0.5 font-medium ${view.chain_ok ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'}`}>
                {view.chain_ok ? 'chain verified' : `broken at #${view.first_bad_seq}`}
              </span>
              <span className="rounded-full bg-slate-100 px-2 py-0.5">{view.source === 'seeded' ? 'seeded history' : 'this run'}</span>
              {captureId && onOpenPaypalTxn && (
                <button
                  onClick={() => onOpenPaypalTxn(captureId)}
                  className="rounded-full bg-indigo-50 px-2 py-0.5 font-medium text-indigo-700 hover:bg-indigo-100"
                >
                  PayPal capture {captureId} →
                </button>
              )}
            </div>
          )}
        </div>
        <button onClick={onClose} className="rounded px-2 py-1 text-slate-500 hover:bg-slate-100" aria-label="Close lineage timeline">✕</button>
      </header>
      <div className="min-h-0 flex-1 overflow-auto p-4">
        {error && <p className="rounded border border-rose-300 bg-rose-50 p-2 text-sm text-rose-800">{error}</p>}
        {!view && !error && <p className="text-sm text-slate-500">Loading…</p>}
        <ol className="space-y-2">
          {view?.entries.map((e) => (
            <li key={e.seq} className="rounded border border-slate-200 p-2 text-xs">
              <button className="flex w-full items-center justify-between text-left" onClick={() => setOpen(open === e.seq ? null : e.seq)}>
                <span>
                  <span className="text-slate-400">#{e.seq}</span> <span className={`rounded px-1.5 py-0.5 font-medium ${KIND_TONE[e.kind] ?? 'bg-slate-100'}`}>{e.kind}</span>{' '}
                  <span className="text-slate-500">{e.stage}</span>
                </span>
                <span className="text-slate-400">{new Date(e.created_at).toLocaleString()}</span>
              </button>
              <div className="mt-1 font-mono text-[11px] text-slate-500">
                prev {short(e.prev_hash, 10)} → <span className="text-slate-800">{short(e.entry_hash, 10)}</span>
              </div>
              {open === e.seq && <pre className="mt-2 max-h-56 overflow-auto rounded bg-slate-50 p-2 text-[11px]">{JSON.stringify(e.payload, null, 2)}</pre>}
            </li>
          ))}
        </ol>
      </div>
    </aside>
  )
}
