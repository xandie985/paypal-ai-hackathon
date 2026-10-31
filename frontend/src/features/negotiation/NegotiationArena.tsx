import type { RunEvent } from '../../api/client'

const SELLERS = ['Northwind Displays', 'Contoso Retail', 'Fabrikam Outlet', 'Globex Wholesale']

const badge: Record<string, string> = {
  COMMITTED: 'bg-emerald-100 text-emerald-800',
  CANCELLED: 'bg-slate-200 text-slate-600',
  HELD: 'bg-amber-100 text-amber-800',
}

export function NegotiationArena({ events }: { events: RunEvent[] }) {
  const neg = events.find((e) => e.event === 'negotiated')
  const discovered = events.filter((e) => e.event === 'discovered')
  if (!neg) return null
  const dropped = neg.dropped as string[]
  const reservations = neg.reservations as Record<string, string>
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="font-semibold">2 · Negotiation arena</h2>
      <p className="text-xs text-slate-500">
        Retail baseline from Channel3: {discovered.map((d) => `${d.category} $${d.baseline}`).join(' · ')}. Sellers are simulated agents.
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-4">
        {SELLERS.map((s) => {
          const gone = dropped.includes(s)
          const won = neg.winner === s
          return (
            <div key={s} className={`rounded border p-3 text-sm ${won ? 'border-emerald-500' : 'border-slate-200'}`}>
              <div className="font-medium">{s}</div>
              {gone ? (
                <span className="mt-2 inline-block rounded bg-rose-100 px-2 py-0.5 text-xs text-rose-800">dropped by schema gate</span>
              ) : (
                <span className={`mt-2 inline-block rounded px-2 py-0.5 text-xs ${badge[reservations[s]] ?? 'bg-slate-100'}`}>
                  {reservations[s] ?? 'no offer'}
                </span>
              )}
              {won && <div className="mt-2 text-xs">final ${String(neg.unit_price)}/unit · saves {String(neg.savings_pct)}% vs baseline</div>}
            </div>
          )
        })}
      </div>
      <p className="mt-2 font-mono text-xs text-slate-500">commitment {String(neg.commitment_hash)}…</p>
    </section>
  )
}
