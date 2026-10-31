import { useEffect, useState } from 'react'
import { api } from './api/client'
import { useRunSession } from './api/useRunSession'
import { AttackButton, RetryButton } from './features/attack/Actions'
import { FirewallDrawer } from './features/firewall/FirewallDrawer'
import { MandateForm } from './features/mandate/MandateForm'
import { NegotiationArena } from './features/negotiation/NegotiationArena'
import { PayPalApprove } from './features/settle/PayPalApprove'
import { Timeline } from './features/timeline/Timeline'

export default function App() {
  const [mode, setMode] = useState<string>('…')
  const { run, events, error, busy, start, act } = useRunSession()
  useEffect(() => {
    api.health().then((h) => setMode(h.paypal_live ? 'live sandbox' : 'replay')).catch(() => setMode('backend offline'))
  }, [])

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
        <h1 className="text-lg font-bold">PactGuard AI</h1>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium">{mode}</span>
      </header>
      <main className="mx-auto max-w-5xl space-y-4 p-6">
        <MandateForm busy={busy} onStart={(m) => start(m)} />
        {error && <p className="rounded border border-rose-300 bg-rose-50 p-2 text-sm text-rose-800">Refused: {error}</p>}
        {run && (
          <>
            <NegotiationArena events={events} />
            <FirewallDrawer
              items={run.items}
              busy={busy}
              onApprove={(l) => act((id) => api.approve(id, l))}
              onReject={(l) => act((id) => api.reject(id, l))}
            />
            <section className="space-y-2 rounded-lg border border-slate-200 bg-white p-4">
              <h2 className="font-semibold">4 · Settle &amp; seal</h2>
              {run.items.map((i) => (
                <div key={i.lineage_id} className="flex flex-wrap items-center gap-3 text-sm">
                  <span className="font-medium">{i.title}</span>
                  <span className="text-xs text-slate-500">{i.status}</span>
                  <PayPalApprove
                    item={i}
                    busy={busy}
                    onPay={() =>
                      act(async (id) => {
                        await api.prepare(id, i.lineage_id)
                        await api.capture(id, i.lineage_id)
                      })
                    }
                  />
                  <RetryButton runId={run.run_id} item={i} />
                </div>
              ))}
            </section>
            <AttackButton runId={run.run_id} onDone={() => act(async () => {})} />
            <Timeline events={events} />
          </>
        )}
      </main>
    </div>
  )
}
