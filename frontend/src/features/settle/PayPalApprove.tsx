import { PayPalButtons, PayPalScriptProvider } from '@paypal/react-paypal-js'
import { useEffect, useState } from 'react'
import { api, ApiError, type Item } from '../../api/client'

type PayPalConfig = { live: boolean; clientId: string | null; currency: string }

// One /api/health call for every card. The client ID is public (the JS SDK loads with it); the secret stays server-side.
let configPromise: Promise<PayPalConfig> | null = null
const loadConfig = () =>
  (configPromise ??= api
    .health()
    .then((h) => ({ live: h.paypal_live, clientId: h.paypal_client_id ?? null, currency: h.currency ?? 'USD' }))
    .catch(() => ({ live: false, clientId: null, currency: 'USD' })))

function usePayPalConfig() {
  const [cfg, setCfg] = useState<PayPalConfig | null>(null)
  useEffect(() => {
    loadConfig().then(setCfg)
  }, [])
  return cfg
}

const describe = (e: unknown) => (e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e))

/**
 * Replay: orders are pre-approved, so one click prepares and captures.
 * Live sandbox: the PayPal JS SDK button. createOrder -> /prepare (writes the seal, returns a CREATED order),
 * the buyer approves in the PayPal popup, onApprove -> /capture (refuses without a seal, trusts only captures[].status).
 */
export function PayPalApprove({
  item,
  runId,
  busy,
  onPay,
  onSettled,
}: {
  item: Item
  runId: string
  busy: boolean
  onPay: () => void
  onSettled: () => void
}) {
  const cfg = usePayPalConfig()
  const [note, setNote] = useState<string | null>(null)

  if (item.status === 'settled')
    return (
      <p className="text-xs text-emerald-800">
        Settled{cfg?.live ? ' in PayPal sandbox' : ' (replay)'} · order <b className="font-mono">{item.order_id}</b> · capture{' '}
        <b className="font-mono">{item.capture_id}</b>
      </p>
    )
  if (item.status !== 'authorized' || !cfg) return null

  if (!cfg.live || !cfg.clientId)
    return (
      <button disabled={busy} onClick={onPay} className="rounded bg-sky-700 px-3 py-1 text-sm font-semibold text-white disabled:opacity-50">
        Pay with PayPal (replay)
      </button>
    )

  return (
    <div className="min-w-64 space-y-1">
      <PayPalScriptProvider options={{ clientId: cfg.clientId, currency: cfg.currency, intent: 'capture' }}>
        <PayPalButtons
          style={{ layout: 'horizontal', height: 35, tagline: false }}
          fundingSource="paypal"
          disabled={busy}
          forceReRender={[item.lineage_id, item.total]}
          createOrder={async () => {
            setNote(null)
            try {
              const prep = await api.prepare(runId, item.lineage_id)
              setNote(`Sandbox order ${prep.order_id} created. Approve it in the PayPal popup.`)
              return prep.order_id
            } catch (e) {
              setNote(`Refused before PayPal: ${describe(e)}`)
              onSettled() // show the guard event
              throw e
            }
          }}
          onApprove={async () => {
            try {
              const cap = await api.capture(runId, item.lineage_id)
              setNote(`Captured ${cap.capture_id}.`)
            } catch (e) {
              setNote(`Capture refused: ${describe(e)}`)
            } finally {
              onSettled()
            }
          }}
          onCancel={() => setNote('Popup closed. The order stays CREATED and sealed; click again to approve it.')}
          onError={(e) => setNote(`PayPal error: ${describe(e)}`)}
        />
      </PayPalScriptProvider>
      {note && <p className="text-xs text-slate-600">{note}</p>}
    </div>
  )
}
