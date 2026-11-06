import type { RunEvent, TranscriptRow } from '../../api/client'
import { money, pct } from '../../lib/format'

const badge: Record<string, string> = {
  COMMITTED: 'bg-emerald-100 text-emerald-800',
  CANCELLED: 'bg-slate-200 text-slate-600',
  HELD: 'bg-amber-100 text-amber-800',
}

export function NegotiationArena({ events }: { events: RunEvent[] }) {
  const neg = events.find((e) => e.event === 'negotiated')
  if (!neg) return null
  const rows = neg.transcript as TranscriptRow[]
  const dropped = neg.dropped as string[]
  const reservations = neg.reservations as Record<string, string>
  const sellers = [...new Set(rows.map((r) => r.seller_id).filter(Boolean))] as string[]
  const turns = [1, 2, 3]
  const cell = (s: string, t: number) => rows.find((r) => r.seller_id === s && r.turn === t && r.from === 'seller')
  const dropTurn = (s: string) => rows.find((r) => r.seller_id === s && r.event === 'dropped_by_schema_gate')?.turn
  const counter = (t: number) => rows.find((r) => r.from === 'buyer' && r.turn === t)
  const finalOffer = (s: string) => cell(s, 3)
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="font-semibold">
        3 · Negotiation <span className="text-xs font-normal text-slate-500">{String(neg.category)} · 3 bounded turns · simulated sellers</span>
      </h2>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[34rem] text-left text-sm">
          <thead className="text-xs text-slate-500">
            <tr>
              <th className="font-normal">Seller</th>
              {turns.map((t) => <th key={t} className="text-right font-normal">Turn {t}</th>)}
              <th className="pl-3 font-normal">Terms</th>
              <th className="font-normal">Reservation</th>
            </tr>
          </thead>
          <tbody>
            {sellers.map((s) => {
              const won = neg.winner === s
              const f = finalOffer(s)
              return (
                <tr key={s} className={`border-t border-slate-100 ${won ? 'bg-emerald-50' : ''}`}>
                  <td className="py-2 pr-3 font-medium">{s}</td>
                  {turns.map((t) => {
                    const c = cell(s, t)
                    const gone = dropTurn(s) === t
                    return (
                      <td key={t} className="text-right tabular-nums">
                        {c ? money(c.unit_price) : gone ? <span className="rounded bg-rose-100 px-1.5 py-0.5 text-xs text-rose-800" title="Malformed output rejected before the buyer saw it">schema gate ✗</span> : <span className="text-slate-300">—</span>}
                      </td>
                    )
                  })}
                  <td className="pl-3 text-xs text-slate-600">{f ? `${f.return_days}d returns · ships ${f.ship_days}d` : dropped.includes(s) ? 'dropped' : ''}</td>
                  <td>{reservations[s] ? <span className={`rounded px-2 py-0.5 text-xs ${badge[reservations[s]] ?? 'bg-slate-100'}`}>{reservations[s]}</span> : <span className="text-xs text-slate-400">{dropped.includes(s) ? 'n/a' : 'ineligible'}</span>}</td>
                </tr>
              )
            })}
            <tr className="border-t border-slate-200 text-xs text-slate-500">
              <td className="py-1">Buyer counter</td>
              {turns.map((t) => <td key={t} className="text-right tabular-nums">{counter(t) ? money(counter(t)!.unit_price) : '—'}</td>)}
              <td colSpan={2} />
            </tr>
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-sm">
        Winner <b>{String(neg.winner)}</b> at <b>{money(neg.unit_price as string)}</b>/unit — <span className="text-emerald-700">{pct(neg.savings_pct as string)} under baseline</span>. Others cancelled; exactly one commitment.
      </p>
      <p className="font-mono text-xs text-slate-400">commitment {String(neg.commitment_hash)}…</p>
    </section>
  )
}
