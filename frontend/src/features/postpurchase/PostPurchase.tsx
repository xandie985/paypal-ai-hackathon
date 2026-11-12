import { useState } from 'react'
import { api, type PostPurchaseStep } from '../../api/client'

const tone: Record<string, string> = {
  PASS: 'bg-emerald-100 text-emerald-800',
  CLEAN: 'bg-emerald-100 text-emerald-800',
  released: 'bg-emerald-100 text-emerald-800',
  FLAGGED: 'bg-amber-100 text-amber-800',
  refused: 'bg-rose-100 text-rose-800',
  skipped: 'bg-slate-200 text-slate-700',
}

// Stages 5 to 7 for one settled purchase: the gates the payout depends on, shown end to end in one click.
export function PostPurchase({ runId, lineage }: { runId: string; lineage: string }) {
  const [steps, setSteps] = useState<PostPurchaseStep[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      setSteps((await api.postPurchase(runId, lineage)).steps)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="space-y-2 rounded border border-slate-200 bg-slate-50 p-3 text-xs" aria-label="Post-purchase checks">
      <div className="flex flex-wrap items-center gap-3">
        <button
          className="rounded bg-indigo-600 px-3 py-1 font-medium text-white disabled:opacity-50"
          disabled={busy || steps !== null}
          onClick={run}
        >
          {busy ? 'Running…' : 'Run post-purchase checks (stages 5–7)'}
        </button>
        <span className="text-slate-500">Verify delivery, reconcile the invoice, then try a payout the gates must refuse before releasing it.</span>
      </div>
      {error && <p className="rounded border border-rose-300 bg-rose-50 p-2 text-rose-800">{error}</p>}
      {steps && (
        <>
          <ol className="space-y-1.5">
            {steps.map((s, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="mt-0.5 w-6 shrink-0 rounded bg-white text-center font-mono text-[11px] text-slate-500">S{s.stage}</span>
                <span className={`mt-0.5 shrink-0 rounded-full px-2 py-0.5 font-medium ${tone[s.outcome] ?? 'bg-slate-100'}`}>{s.outcome}</span>
                <span>
                  <b>{s.title}.</b> <span className="text-slate-600">{s.detail}</span>
                </span>
              </li>
            ))}
          </ol>
          <p className="text-slate-500">The carrier report and the vendor invoices are scripted. The gates, ledger entries and payout call are the real stage code.</p>
        </>
      )}
    </section>
  )
}
