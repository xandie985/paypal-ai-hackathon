import { useEffect, useState } from 'react'
import { api } from './api/client'
import { useRunSession } from './api/useRunSession'
import { AttackButton } from './features/attack/Actions'
import { DealCard } from './features/deal/DealCard'
import { LedgerPanel } from './features/ledger/LedgerPanel'
import { MarketPanel } from './features/market/MarketPanel'
import { MandateForm } from './features/mandate/MandateForm'
import { NegotiationArena } from './features/negotiation/NegotiationArena'
import { SummaryStrip } from './features/summary/SummaryStrip'
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
            <SummaryStrip run={run} />
            <MarketPanel events={events} />
            <NegotiationArena events={events} />
            <section className="space-y-3">
              <h2 className="font-semibold">4 · Deals · firewall · settlement</h2>
              {run.items.map((i) => (
                <DealCard
                  key={i.lineage_id}
                  item={i}
                  runId={run.run_id}
                  busy={busy}
                  onApprove={() => act((id) => api.approve(id, i.lineage_id))}
                  onReject={() => act((id) => api.reject(id, i.lineage_id))}
                  onPay={() =>
                    act(async (id) => {
                      await api.prepare(id, i.lineage_id)
                      await api.capture(id, i.lineage_id)
                    })
                  }
                />
              ))}
            </section>
            <AttackButton runId={run.run_id} onDone={() => act(async () => {})} />
            <LedgerPanel runId={run.run_id} entries={run.ledger_entries} />
            <Timeline events={events} />
          </>
        )}
      </main>
    </div>
  )
}
