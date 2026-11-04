import { useState } from 'react'
import type { MandateInput } from '../../api/client'

const DEFAULTS: MandateInput = {
  principal: 'ops@acme.example',
  purpose: 'Equip a 5-person engineering office',
  budget: '2200',
  auto_threshold: '300',
  per_txn_cap: '1500',
  vendor_allowlist: ['Northwind Displays', 'Contoso Retail', 'amazon.com', 'bestbuy.com', 'walmart.com', 'target.com', 'newegg.com', 'bhphotovideo.com', 'ebay.com'],
  allowed_categories: ['monitors', 'webcams', 'microphones'],
  min_return_days: 30,
  mode: 'auto',
}

const field = 'mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm'

export function MandateForm({ busy, onStart }: { busy: boolean; onStart: (m: MandateInput) => void }) {
  const [m, setM] = useState(DEFAULTS)
  const num = (k: 'budget' | 'auto_threshold' | 'per_txn_cap') => (
    <label className="text-xs font-medium text-slate-600">
      {k.replace('_', ' ')} (USD)
      <input className={field} value={m[k]} inputMode="decimal" onChange={(e) => setM({ ...m, [k]: e.target.value })} />
    </label>
  )
  const list = (k: 'vendor_allowlist' | 'allowed_categories', label: string) => (
    <label className="text-xs font-medium text-slate-600">
      {label} (comma separated)
      <input className={field} value={m[k].join(', ')} onChange={(e) => setM({ ...m, [k]: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })} />
    </label>
  )
  return (
    <form
      className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault()
        onStart(m)
      }}
    >
      <h2 className="font-semibold sm:col-span-2">1 · Mandate</h2>
      {num('budget')}
      {num('auto_threshold')}
      {num('per_txn_cap')}
      <label className="text-xs font-medium text-slate-600">
        min return days
        <input className={field} type="number" value={m.min_return_days} onChange={(e) => setM({ ...m, min_return_days: Number(e.target.value) })} />
      </label>
      {list('vendor_allowlist', 'vendor allowlist')}
      {list('allowed_categories', 'categories')}
      <label className="text-xs font-medium text-slate-600">
        mode
        <select className={field} value={m.mode} onChange={(e) => setM({ ...m, mode: e.target.value as MandateInput['mode'] })}>
          <option value="auto">auto (small buys settle alone)</option>
          <option value="review_first">review first (human approves everything)</option>
        </select>
      </label>
      <button disabled={busy} className="self-end rounded bg-indigo-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">
        {busy ? 'Running…' : 'Run agent'}
      </button>
    </form>
  )
}
