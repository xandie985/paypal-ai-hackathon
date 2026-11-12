import { useEffect, useState } from 'react'
import type { MandateInput, NeedInput } from '../../api/client'
import { DEFAULT_NEEDS, DEFAULTS, PRESET_STRICT } from './defaults'

const MAX_NEEDS = 6

const list = (s: string) =>
  s
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean)

export function MandateForm({
  busy,
  onStart,
  onMandateChange,
  sandboxAvailable = false,
}: {
  busy: boolean
  onStart: (m: MandateInput, sandbox?: boolean, needs?: NeedInput[]) => void
  sandboxAvailable?: boolean
  onMandateChange?: (m: MandateInput) => void
}) {
  const [m, setM] = useState<MandateInput>(DEFAULTS)
  const [confirmSandbox, setConfirmSandbox] = useState(false)
  const [needs, setNeeds] = useState<NeedInput[]>(DEFAULT_NEEDS)
  const [activePreset, setActivePreset] = useState<'office' | 'strict' | null>('office')
  // The two list fields keep what was typed: rebuilding the text from the parsed list would swallow each comma as it is typed.
  const [vendorText, setVendorText] = useState(DEFAULTS.vendor_allowlist.join(', '))
  const [categoryText, setCategoryText] = useState(DEFAULTS.allowed_categories.join(', '))

  useEffect(() => {
    onMandateChange?.(m)
  }, [m, onMandateChange])

  const applyPreset = (preset: 'office' | 'strict') => {
    const next = preset === 'office' ? DEFAULTS : PRESET_STRICT
    setM(next)
    setVendorText(next.vendor_allowlist.join(', '))
    setCategoryText(next.allowed_categories.join(', '))
    setActivePreset(preset)
  }

  const errs: string[] = []
  const budgetNum = Number(m.budget)
  const autoNum = Number(m.auto_threshold)
  const capNum = Number(m.per_txn_cap)
  if (!(budgetNum > 0)) errs.push('Budget must be greater than 0.')
  if (autoNum < 0) errs.push('Auto threshold cannot be negative.')
  if (autoNum > budgetNum) errs.push('Auto threshold cannot exceed budget.')
  if (!(capNum > 0)) errs.push('Cap must be greater than 0.')
  if (capNum > budgetNum) errs.push('Cap cannot exceed budget.')
  if (autoNum > capNum) errs.push('Auto threshold cannot exceed the per-transaction cap.')
  if (!Number.isInteger(m.min_return_days) || m.min_return_days < 0) errs.push('Min return days must be a whole number, 0 or more.')
  if (m.vendor_allowlist.length === 0) errs.push('Add at least one vendor to the allowlist.')
  if (m.allowed_categories.length === 0) errs.push('Add at least one allowed category.')
  if (needs.length === 0) errs.push('Add at least one item to buy.')
  if (needs.some((n) => !n.description.trim() || !n.category.trim())) errs.push('Every item needs a description and a category.')
  if (needs.some((n) => !Number.isInteger(n.quantity) || n.quantity < 1 || n.quantity > 25)) errs.push('Quantities must be whole numbers from 1 to 25.')
  const setNeed = (i: number, patch: Partial<NeedInput>) => setNeeds(needs.map((n, j) => (j === i ? { ...n, ...patch } : n)))

  // Compact fields for the item rows. No width of their own, so each row can size them.
  const cell =
    'rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-800 focus:border-indigo-500 focus:outline-hidden focus:ring-2 focus:ring-indigo-100'

  const inputClass =
    'mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-xs focus:border-indigo-500 focus:outline-hidden focus:ring-2 focus:ring-indigo-100'

  return (
    <form
      className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
      onSubmit={(e) => {
        e.preventDefault()
        if (errs.length === 0 && !busy) {
          onStart(m, false, needs)
        }
      }}
    >
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div className="flex items-center gap-2 font-semibold text-slate-900">
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-indigo-50 text-indigo-600">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
          </span>
          <h3>1 · Mandate</h3>
        </div>
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Policy Bounds</span>
      </div>

      {/* Preset pills */}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => applyPreset('office')}
          className={`flex-1 rounded-full px-3 py-1.5 text-xs font-medium transition ${
            activePreset === 'office'
              ? 'border border-indigo-200 bg-indigo-50 text-indigo-700'
              : 'border border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100'
          }`}
        >
          Office setup ($2.2k)
        </button>
        <button
          type="button"
          onClick={() => applyPreset('strict')}
          className={`flex-1 rounded-full px-3 py-1.5 text-xs font-medium transition ${
            activePreset === 'strict'
              ? 'border border-indigo-200 bg-indigo-50 text-indigo-700'
              : 'border border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100'
          }`}
        >
          Strict review ($1.2k)
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs font-medium text-slate-600">Budget (USD)</label>
          <input
            className={inputClass}
            type="number"
            min="1"
            step="any"
            value={m.budget}
            onChange={(e) => {
              setActivePreset(null)
              setM({ ...m, budget: e.target.value })
            }}
          />
        </div>
        <div>
          <label className="text-xs font-medium text-slate-600">Auto threshold</label>
          <input
            className={inputClass}
            type="number"
            min="0"
            step="any"
            value={m.auto_threshold}
            onChange={(e) => {
              setActivePreset(null)
              setM({ ...m, auto_threshold: e.target.value })
            }}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs font-medium text-slate-600">Per-txn cap</label>
          <input
            className={inputClass}
            type="number"
            min="1"
            step="any"
            value={m.per_txn_cap}
            onChange={(e) => {
              setActivePreset(null)
              setM({ ...m, per_txn_cap: e.target.value })
            }}
          />
        </div>
        <div>
          <label className="text-xs font-medium text-slate-600">Min return days</label>
          <input
            className={inputClass}
            type="number"
            min="0"
            value={m.min_return_days}
            onChange={(e) => {
              setActivePreset(null)
              setM({ ...m, min_return_days: Number(e.target.value) })
            }}
          />
        </div>
      </div>

      <div>
        <label className="text-xs font-medium text-slate-600">Vendor allowlist</label>
        <textarea
          rows={2}
          className={`${inputClass} resize-none font-mono text-xs`}
          value={vendorText}
          onChange={(e) => {
            setActivePreset(null)
            setVendorText(e.target.value)
            setM({ ...m, vendor_allowlist: list(e.target.value) })
          }}
        />
        <p className="mt-1 text-[11px] text-slate-400">Comma-separated domains or merchant names. Rejects unlisted sellers.</p>
      </div>

      <div>
        <label className="text-xs font-medium text-slate-600">Allowed categories</label>
        <input
          className={inputClass}
          value={categoryText}
          onChange={(e) => {
            setActivePreset(null)
            setCategoryText(e.target.value)
            setM({ ...m, allowed_categories: list(e.target.value) })
          }}
        />
      </div>

      <div>
        <label className="text-xs font-medium text-slate-600">Approval mode</label>
        <div className="mt-1 grid grid-cols-2 gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1 text-xs font-medium">
          <button
            type="button"
            onClick={() => {
              setActivePreset(null)
              setM({ ...m, mode: 'auto' })
            }}
            className={`rounded-md py-1.5 transition ${
              m.mode === 'auto' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-500 hover:text-slate-900'
            }`}
          >
            Auto + review gate
          </button>
          <button
            type="button"
            onClick={() => {
              setActivePreset(null)
              setM({ ...m, mode: 'review_first' })
            }}
            className={`rounded-md py-1.5 transition ${
              m.mode === 'review_first' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-500 hover:text-slate-900'
            }`}
          >
            Review everything
          </button>
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between">
          <label className="text-xs font-medium text-slate-600">What to buy</label>
          <button
            type="button"
            disabled={needs.length >= MAX_NEEDS}
            onClick={() => setNeeds([...needs, { description: '', category: m.allowed_categories[0] ?? '', quantity: 1, method: 'direct' }])}
            className="text-xs font-semibold text-indigo-700 hover:underline disabled:opacity-40"
          >
            + Add item
          </button>
        </div>
        <ul className="mt-1 space-y-2">
          {needs.map((n, i) => {
            const outside = n.category.trim() !== '' && !m.allowed_categories.includes(n.category.trim())
            return (
              <li key={i} className="rounded-lg border border-slate-200 bg-slate-50 p-2">
                <div className="flex items-center gap-2">
                  <input
                    aria-label={`Item ${i + 1} description`}
                    className={`${cell} min-w-0 flex-1`}
                    value={n.description}
                    placeholder="e.g. 27in 4K monitor"
                    onChange={(e) => setNeed(i, { description: e.target.value })}
                  />
                  <input
                    aria-label={`Item ${i + 1} quantity`}
                    className={`${cell} w-16 shrink-0 text-center`}
                    type="number"
                    min="1"
                    max="25"
                    step="1"
                    value={n.quantity}
                    onChange={(e) => setNeed(i, { quantity: Number(e.target.value) })}
                  />
                  <button
                    type="button"
                    aria-label={`Remove item ${i + 1}`}
                    onClick={() => setNeeds(needs.filter((_, j) => j !== i))}
                    className="rounded px-1.5 text-lg leading-none text-slate-400 hover:text-rose-600"
                  >
                    ×
                  </button>
                </div>
                <div className="mt-1.5 grid grid-cols-2 gap-2">
                  <input
                    aria-label={`Item ${i + 1} category`}
                    className={`${cell} w-full min-w-0`}
                    value={n.category}
                    placeholder="category"
                    onChange={(e) => setNeed(i, { category: e.target.value })}
                  />
                  <select
                    aria-label={`Item ${i + 1} method`}
                    className={`${cell} w-full min-w-0`}
                    value={n.method}
                    onChange={(e) => setNeed(i, { method: e.target.value as NeedInput['method'] })}
                  >
                    <option value="direct">Direct buy</option>
                    <option value="negotiate">Negotiate with sellers</option>
                  </select>
                </div>
                {outside && <p className="mt-1 text-[11px] text-amber-700">Not in the allowed categories: the firewall will block it.</p>}
              </li>
            )
          })}
        </ul>
      </div>

      {errs.length > 0 && (
        <div className="rounded-lg bg-rose-50 p-2.5 text-xs font-medium text-rose-700">
          {errs[0]}
        </div>
      )}

      <button
        type="submit"
        disabled={busy || errs.length > 0}
        className="w-full rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-sky-600 py-3 text-sm font-bold text-white shadow-md shadow-indigo-500/20 transition hover:from-blue-700 hover:via-indigo-700 hover:to-sky-700 active:scale-[0.99] disabled:opacity-50"
      >
        {busy ? (
          <span className="flex items-center justify-center gap-2">
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            Running procurement agent…
          </span>
        ) : (
          <span className="flex items-center justify-center gap-2">
            <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z" />
            </svg>
            Run agent
          </span>
        )}
      </button>

      {sandboxAvailable && (
        <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50 p-3">
          {!confirmSandbox ? (
            <button
              type="button"
              disabled={busy || errs.length > 0}
              onClick={() => setConfirmSandbox(true)}
              className="w-full rounded-lg border border-amber-300 bg-white py-2 text-sm font-bold text-amber-900 transition hover:bg-amber-100 disabled:opacity-50"
            >
              Run in PayPal sandbox
            </button>
          ) : (
            <>
              <p className="text-xs text-amber-900">
                This creates <b>real orders in our PayPal sandbox</b> and charges its saved wallet (test money). Held purchases are paid
                from the same wallet once you approve them. Limited to a few runs per hour.
              </p>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  disabled={busy || errs.length > 0}
                  onClick={() => {
                    setConfirmSandbox(false)
                    onStart(m, true, needs)
                  }}
                  className="rounded-lg bg-amber-600 py-2 text-xs font-bold text-white hover:bg-amber-700 disabled:opacity-50"
                >
                  Confirm sandbox run
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmSandbox(false)}
                  className="rounded-lg border border-amber-300 bg-white py-2 text-xs font-bold text-amber-900 hover:bg-amber-100"
                >
                  Cancel
                </button>
              </div>
            </>
          )}
        </div>
      )}

      <p className="text-center text-xs text-slate-400">
        Deterministic spend firewall. Untrusted LLMs cannot authorize or disburse payouts.
      </p>
    </form>
  )
}
