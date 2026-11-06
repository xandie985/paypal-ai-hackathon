import type { Item } from '../../api/client'

const route = {
  AUTO_SETTLE: { label: 'Auto-settle', cls: 'border-emerald-500 bg-emerald-50' },
  HUMAN_APPROVAL: { label: 'Needs your approval', cls: 'border-amber-500 bg-amber-50' },
  BLOCKED: { label: 'Blocked', cls: 'border-rose-500 bg-rose-50' },
} as const

export function RouteCard({ item, busy, onApprove, onReject }: { item: Item; busy: boolean; onApprove: () => void; onReject: () => void }) {
  const d = item.decision
  if (!d) return null
  const approved = d.route === 'HUMAN_APPROVAL' && ['authorized', 'settled'].includes(item.status)
  const r = approved ? { label: 'Approved by human ✓', cls: 'border-emerald-500 bg-emerald-50' } : route[d.route]
  return (
    <div className={`rounded-lg border-2 p-3 ${r.cls}`}>
      <div className="flex items-baseline justify-between">
        <span className="font-medium">{item.title}</span>
        <span className="text-sm font-semibold">{r.label}</span>
      </div>
      <ul className="mt-2 space-y-0.5 text-xs">
        {d.factors.map((f) => (
          <li key={f.name}>
            <span className={f.passed ? 'text-emerald-700' : 'text-rose-700'}>{f.passed ? '✓' : '✗'}</span> <b>{f.name}</b> — {f.detail}
          </li>
        ))}
      </ul>
      <p className="mt-1 text-xs text-slate-500">decided in {d.latency_ms} ms · deterministic, no LLM</p>
      {item.status === 'awaiting_approval' && (
        <div className="mt-2 flex gap-2">
          <button disabled={busy} onClick={onApprove} className="rounded bg-emerald-600 px-3 py-1 text-sm font-semibold text-white disabled:opacity-50">
            Approve
          </button>
          <button disabled={busy} onClick={onReject} className="rounded border border-slate-400 px-3 py-1 text-sm disabled:opacity-50">
            Reject
          </button>
        </div>
      )}
    </div>
  )
}
