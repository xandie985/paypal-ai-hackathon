import type { Item } from '../../api/client'

// Replay orders are pre-approved, so one click prepares and captures. Live mode swaps this for the PayPal JS SDK button.
export function PayPalApprove({ item, busy, onPay }: { item: Item; busy: boolean; onPay: () => void }) {
  if (item.status === 'settled')
    return (
      <p className="text-xs text-emerald-800">
        Settled · order <b>{item.order_id}</b> · capture <b>{item.capture_id}</b>
      </p>
    )
  if (item.status !== 'authorized') return null
  return (
    <button disabled={busy} onClick={onPay} className="rounded bg-sky-700 px-3 py-1 text-sm font-semibold text-white disabled:opacity-50">
      Pay with PayPal (replay)
    </button>
  )
}
