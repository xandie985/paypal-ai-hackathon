import { useState } from 'react'
import { api, type Item } from '../../api/client'

export function AttackButton({ runId, onDone }: { runId: string; onDone: () => void }) {
  const [out, setOut] = useState<string>('')
  return (
    <div>
      <button
        className="rounded bg-rose-700 px-3 py-1 text-sm font-semibold text-white"
        onClick={async () => {
          const r = await api.attack(runId)
          setOut(`${r.route} in ${r.latency_ms} ms — ${r.reasons[0] ?? ''}`)
          onDone()
        }}
      >
        Simulate prompt-injection attack
      </button>
      {out && <p className="mt-1 text-xs text-rose-800">{out}</p>}
    </div>
  )
}

export function RetryButton({ runId, item }: { runId: string; item: Item }) {
  const [out, setOut] = useState('')
  if (!item.order_id) return null
  return (
    <span>
      <button
        className="rounded border border-slate-400 px-2 py-0.5 text-xs"
        onClick={async () => {
          const r = await api.retry(runId, item.lineage_id)
          setOut(r.same_order ? `same order ${r.order_id} — no double charge` : `DIFFERENT order ${r.order_id}`)
        }}
      >
        Retry create-order
      </button>{' '}
      <span className="text-xs text-slate-600">{out}</span>
    </span>
  )
}
