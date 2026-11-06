import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, type WebhookEvent } from '../../api/client'

const fmt = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium' })
const err = (e: unknown) => (e instanceof ApiError ? e.message : String(e))

// Stage 7. PayPal's deliveries are verified against the raw bytes, de-duplicated by event id and stored
// in the sealed ledger, so a retry or a replay can never double-apply an event.
export function WebhookInspector({ live }: { live: boolean }) {
  const [events, setEvents] = useState<WebhookEvent[]>([])
  const [shown, setShown] = useState<{ id: string; body: unknown } | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const load = useCallback(() => {
    api.webhooks().then((r) => setEvents(r.events)).catch((e) => setMsg(`Could not load webhooks: ${err(e)}`))
  }, [])
  useEffect(load, [load])

  const simulate = async (eventId?: string) => {
    try {
      const out = await api.simulateWebhook({ event_id: eventId, lineage_id: events[0]?.lineage_id })
      setMsg(out.duplicate ? `Duplicate ignored: ${out.event_id} was already stored.` : `Accepted ${out.event_id}.`)
      load()
    } catch (e) {
      setMsg(err(e))
    }
  }
  const replay = (id: string) => api.replayWebhook(id).then((body) => setShown({ id, body })).catch((e) => setMsg(err(e)))

  return (
    <section className="space-y-2 rounded border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">7 · Webhook inspector</h2>
        <div className="flex gap-1 text-xs">
          {!live && (
            <>
              <button className="rounded bg-indigo-600 px-2 py-1 font-medium text-white" onClick={() => simulate()}>
                Simulate delivery
              </button>
              <button className="rounded border border-slate-300 px-2 py-1 font-medium disabled:opacity-40" disabled={!events.length} onClick={() => simulate(events[0].event_id)}>
                Redeliver latest
              </button>
            </>
          )}
          <button className="rounded px-2 py-1 font-medium text-slate-600 hover:bg-slate-100" onClick={load}>
            Refresh
          </button>
        </div>
      </div>
      <p className="text-xs text-slate-500">
        Deliveries to <code>POST /api/webhooks/paypal</code> are {live ? 'verified by PayPal against the exact bytes received' : 'accepted with a replay signature'}, de-duplicated by event id, and sealed in the ledger.
      </p>
      {msg && <p className="text-xs text-slate-700">{msg}</p>}
      {events.length === 0 ? (
        <p className="text-sm text-slate-500">No events yet.</p>
      ) : (
        <table className="w-full text-left text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1 pr-2">Received</th>
              <th className="pr-2">Event</th>
              <th className="pr-2">Lineage</th>
              <th className="pr-2">Event ID</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {events.slice(0, 8).map((e) => (
              <tr key={e.event_id} className="border-t border-slate-100">
                <td className="py-1 pr-2 whitespace-nowrap">{fmt.format(new Date(e.received_at))}</td>
                <td className="pr-2 font-medium">{e.event_type}</td>
                <td className="pr-2 font-mono">{e.lineage_id}</td>
                <td className="pr-2 font-mono">{e.event_id}</td>
                <td className="text-right">
                  <button className="font-medium text-indigo-700 hover:underline" onClick={() => replay(e.event_id)}>
                    Replay
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {shown && (
        <pre className="max-h-48 overflow-auto rounded bg-slate-900 p-2 text-xs text-slate-100" aria-label={`Stored event ${shown.id}`}>
          {JSON.stringify(shown.body, null, 2)}
        </pre>
      )}
    </section>
  )
}
