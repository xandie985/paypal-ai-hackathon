import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, type DeliveryInput, type DisputeDetail, type DisputeSummary, type RunSnapshot } from '../../api/client'
import { money, pct } from '../../lib/format'

const LABEL: Record<string, string> = {
  contest: 'Contest with sealed evidence',
  inform: 'Share tracking and wait',
  partial_refund: 'Refund the overcharge',
  refund_with_return: 'Refund on return',
  acknowledge_return: 'Confirm return received & refund',
  accept: 'Accept and refund',
}

// Replay scenarios: what a buyer might write for each PayPal reason.
const SCENARIOS: { reason: string; label: string; note: string }[] = [
  { reason: 'MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED', label: 'Stopped working (not as described)', note: 'it was working fine and then it stopped. i will have to return it' },
  { reason: 'MERCHANDISE_OR_SERVICE_NOT_RECEIVED', label: 'Never arrived', note: 'my order never arrived' },
  { reason: 'DUPLICATE_TRANSACTION', label: 'Charged twice', note: 'i was charged twice for this' },
  { reason: 'INCORRECT_AMOUNT', label: 'Wrong amount', note: 'the amount charged is not what i agreed to' },
  { reason: 'UNAUTHORISED', label: "I didn't make this payment", note: 'i did not authorise this payment' },
  { reason: 'CREDIT_NOT_PROCESSED', label: 'Refund not received', note: 'you promised a refund and it never came' },
]

const err = (e: unknown) => (e instanceof ApiError ? e.message : String(e))
const fmt = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })
const fmtDay = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })
// PayPal and the ledger send ISO-8601 (UTC). Shown in the viewer's own time zone.
const when = (ts: string | null | undefined, dayOnly = false) => (ts ? (dayOnly ? fmtDay : fmt).format(new Date(ts)) : '—')
const WHO: Record<string, string> = { ledger: 'bg-indigo-100 text-indigo-800', buyer: 'bg-amber-100 text-amber-800', us: 'bg-emerald-100 text-emerald-800', paypal: 'bg-sky-100 text-sky-800', seller: 'bg-emerald-100 text-emerald-800', deadline: 'bg-rose-100 text-rose-800' }

// Stage 8. The agent assesses; a human reads the draft and decides. Nothing reaches PayPal without "Send".
export function DisputeDesk({ run, live }: { run: RunSnapshot | null; live: boolean }) {
  const [list, setList] = useState<DisputeSummary[]>([])
  const [sel, setSel] = useState<string | null>(null)
  const [detail, setDetail] = useState<DisputeDetail | null>(null)
  const [option, setOption] = useState<string>('')
  const [note, setNote] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [scenario, setScenario] = useState(SCENARIOS[0].reason)
  const [track, setTrack] = useState<Pick<DeliveryInput, 'carrier' | 'tracking_number' | 'tracking_status'>>({ carrier: 'UPS', tracking_number: '', tracking_status: 'DELIVERED' })
  const [loading, setLoading] = useState(false)
  const [inspect, setInspect] = useState({ condition: 'ITEM_RECEIVED', note: '' })

  const load = useCallback(async () => {
    try {
      setList(await api.disputes())
    } catch (e) {
      setMsg(`Could not load disputes: ${err(e)}`)
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => {
    api
      .disputes()
      .then(setList)
      .catch((e) => setMsg(`Could not load disputes: ${err(e)}`))
    const timer = setInterval(() => {
      if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
        load()
      }
    }, 10000)
    return () => clearInterval(timer)
  }, [load])

  const open = async (id: string) => {
    setSel(id)
    const d = await api.dispute(id)
    setDetail(d)
    const pick = d.assessment.recommended ?? d.assessment.options.find((o) => o.available && !o.excluded_by)?.option ?? 'contest'
    setOption(pick)
    setNote(d.drafts[pick] ?? '')
  }

  const choose = (o: string) => {
    setOption(o)
    setNote(detail?.drafts[o] ?? '')
  }

  const act = async (fn: () => Promise<void>) => {
    setBusy(true)
    setMsg(null)
    try {
      await fn()
    } catch (e) {
      setMsg(err(e))
    } finally {
      setBusy(false)
    }
  }

  const settled = run?.items.filter((i) => i.status === 'settled') ?? []
  const a = detail?.assessment
  const f = a?.facts
  const chosen = a?.options.find((o) => o.option === option)

  return (
    <section className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">
          8 · Dispute desk <span className="text-xs font-normal text-slate-500">PayPal disputes answered from the sealed ledger</span>
        </h2>
        <div className="flex flex-wrap gap-2 text-xs">
          {!live && settled.length > 0 && (
            <>
              <select className="rounded border border-slate-300 px-2 py-1" value={scenario} onChange={(e) => setScenario(e.target.value)}>
                {SCENARIOS.map((s) => (
                  <option key={s.reason} value={s.reason}>{s.label}</option>
                ))}
              </select>
              <select
                className="rounded border border-slate-300 px-2 py-1"
                value=""
                disabled={busy}
                onChange={(e) => {
                  const lid = e.target.value
                  const s = SCENARIOS.find((x) => x.reason === scenario)!
                  if (lid)
                    act(async () => {
                      const r = await api.simulateDispute(run!.run_id, lid, s.reason, s.note)
                      await load()
                      await open(r.dispute_id)
                    })
                }}
              >
                <option value="">Simulate it on…</option>
                {settled.map((i) => (
                  <option key={i.lineage_id} value={i.lineage_id}>{i.title}</option>
                ))}
              </select>
            </>
          )}
          <button
            className="rounded border border-slate-300 px-2 py-1 disabled:opacity-50"
            disabled={loading}
            onClick={() => {
              setLoading(true)
              load()
            }}
          >
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      {list.length === 0 ? (
        <p className="text-sm text-slate-500">No open disputes.</p>
      ) : (
        <table className="w-full text-sm [&_td]:px-2 [&_th]:px-2">
          <thead className="text-left text-xs text-slate-500">
            <tr><th>Opened</th><th>Case</th><th>Reason</th><th>Item</th><th className="text-right">Held</th><th>State</th><th>Respond by</th><th>Evidence</th><th>Agent suggests</th></tr>
          </thead>
          <tbody>
            {list.map((d) => (
              <tr key={d.case.dispute_id} onClick={() => open(d.case.dispute_id)} className={`cursor-pointer border-t hover:bg-slate-50 ${sel === d.case.dispute_id ? 'bg-indigo-50' : ''}`}>
                <td className="whitespace-nowrap text-xs">{when(d.case.created)}</td>
                <td className="font-mono text-xs">{d.case.dispute_id}</td>
                <td className="text-xs">{d.reason_label}</td>
                <td>{d.case.item_name}</td>
                <td className="text-right">{money(d.case.amount)}</td>
                <td className="text-xs">{d.case.stage} · {d.case.status.replaceAll('_', ' ').toLowerCase()}</td>
                <td className="whitespace-nowrap text-xs">
                  {d.case.status === 'WAITING_FOR_SELLER_RESPONSE' ? <>{when(d.case.due_date, true)} <span className={d.days_left != null && d.days_left <= 3 ? 'text-rose-700' : 'text-slate-500'}>({d.days_left}d)</span></> : '—'}
                </td>
                <td>{d.lineage_found ? <span className="text-emerald-700">sealed ✓</span> : <span className="text-rose-700">not found</span>}</td>
                <td className="text-xs">{d.recommended ? LABEL[d.recommended] : d.state_note ? <span className="text-slate-500">{d.state_note}</span> : 'review manually'}{d.flags.length > 0 && <span className="ml-1 text-amber-700" title={d.flags.join('\n')}>⚑{d.flags.length}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {detail && a && f && (
        <div className="space-y-3 border-t pt-3">
          {a.state_note && <p className="rounded bg-sky-50 px-2 py-1 text-xs text-sky-900">{a.state_note}</p>}
          {a.flags.map((fl) => (
            <p key={fl} className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-900">⚑ {fl}</p>
          ))}
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-2 text-sm">
              <div>
                <span className="font-semibold">{a.reason_label}</span>
                {a.playbook && <span className="text-xs text-slate-500"> · playbook: {a.playbook}</span>}
              </div>
              <blockquote className="rounded bg-slate-50 p-2 text-xs italic text-slate-700">“{detail.case.buyer_note}”</blockquote>
              <ul className="space-y-0.5 text-xs">
                {!f.lineage_found && <li className="text-rose-700">No sealed record matches this payment. The agent won't contest without evidence.</li>}
                {f.lineage_found && (
                  <>
                    <li>Order <b className="font-mono">{String(f.order_id)}</b> sealed {when(String(f.sealed_at))} ({String(f.days_since_purchase)} days ago)</li>
                    <li>Sealed price {money(String(f.sealed_amount))} · captured {money(String(f.captured_amount))} · disputed {money(detail.case.amount)}</li>
                    <li>Return window: {f.sealed_return_days == null ? 'hidden by the merchant' : `${f.sealed_return_days} days`}{f.within_return_window ? ' · still open' : ''}</li>
                    <li>Delivery: {f.delivery_status ? `${String(f.delivery_status).toLowerCase().replace('_', ' ')} (${(f.tracking as { carrier: string; number: string }).carrier} ${(f.tracking as { carrier: string; number: string }).number})` : 'no tracking recorded'}</li>
                    <li>Human approved before payment: {f.human_approved ? 'yes' : 'no'} · ledger chain {f.chain_ok ? 'intact' : 'BROKEN'}</li>
                    <li>Missing evidence: {(f.missing_evidence as string[]).join(', ') || 'none'}</li>
                    {Boolean(f.return_tracking) && (
                      <li className="font-semibold text-emerald-800">
                        Buyer return tracking: {(f.return_tracking as { carrier: string; number: string }).carrier} {(f.return_tracking as { carrier: string; number: string }).number}
                      </li>
                    )}
                  </>
                )}
                <li>Buyer's claim reads as: <b>{f.claim.replace('_', ' ')}</b> · win odds {pct(a.win_odds * 100, 0)}</li>
              </ul>
              {f.lineage_found && (
                <a className="text-xs text-indigo-700 hover:underline" href={api.briefUrl(detail.case.dispute_id)}>Download evidence brief (PDF)</a>
              )}

              {Boolean(f.return_tracking) && !f.return_received && detail.case.actions.includes('acknowledge_return_item') && (
                <div className="space-y-1 rounded border border-amber-300 bg-amber-50 p-2 text-xs">
                  <div className="font-semibold text-amber-900">When the parcel arrives, open it and record what was inside. The refund only goes out after this.</div>
                  <div className="flex flex-wrap items-center gap-1">
                    <select className="rounded border px-1" value={inspect.condition} onChange={(e) => setInspect({ ...inspect, condition: e.target.value })}>
                      {[['ITEM_RECEIVED', 'Item back, as sold'], ['DAMAGED', 'Damaged'], ['MISSING_ITEMS', 'Parts missing'], ['EMPTY_PACKAGE_OR_DIFFERENT', 'Empty box / different item'], ['ITEM_NOT_RECEIVED', 'Parcel never arrived']].map(([v, l]) => (
                        <option key={v} value={v}>{l}</option>
                      ))}
                    </select>
                    <input className="min-w-40 flex-1 rounded border px-1" placeholder="what you found (optional)" value={inspect.note} onChange={(e) => setInspect({ ...inspect, note: e.target.value })} />
                    <button
                      className="rounded border border-amber-400 bg-white px-2"
                      disabled={busy}
                      onClick={() =>
                        act(async () => {
                          await api.returnReceived(detail.case.dispute_id, inspect.condition, inspect.note)
                          setMsg('Inspection sealed in the ledger.')
                          await open(detail.case.dispute_id)
                        })
                      }
                    >
                      Record inspection
                    </button>
                  </div>
                </div>
              )}
              {Boolean(f.return_received) && (
                <p className="text-xs text-emerald-800">Return inspected: {String((f.return_received as { condition: string }).condition).replaceAll('_', ' ').toLowerCase()}</p>
              )}
              {f.lineage_found && !f.delivered && (
                <div className="flex flex-wrap items-center gap-1 rounded border border-dashed border-slate-300 p-2 text-xs">
                  <span className="text-slate-600">Record tracking (stage 5):</span>
                  <input className="w-16 rounded border px-1" value={track.carrier} onChange={(e) => setTrack({ ...track, carrier: e.target.value })} />
                  <input className="w-28 rounded border px-1" placeholder="tracking no." value={track.tracking_number} onChange={(e) => setTrack({ ...track, tracking_number: e.target.value })} />
                  <select className="rounded border px-1" value={track.tracking_status} onChange={(e) => setTrack({ ...track, tracking_status: e.target.value as DeliveryInput['tracking_status'] })}>
                    {['DELIVERED', 'IN_TRANSIT', 'LOST'].map((s) => <option key={s}>{s}</option>)}
                  </select>
                  <button
                    className="rounded border border-slate-300 px-2"
                    disabled={busy || !track.tracking_number}
                    onClick={() =>
                      act(async () => {
                        const today = new Date().toISOString().slice(0, 10)
                        const due = new Date(Date.now() + 3 * 864e5).toISOString().slice(0, 10)
                        const r = await api.recordDelivery({ lineage_id: a.lineage_id!, ...track, delivered_on: track.tracking_status === 'DELIVERED' ? today : undefined, due_by: due })
                        setMsg(`Tracking sealed: ${r.verdict}${r.problems.length ? ` (${r.problems.join('; ')})` : ''}`)
                        await open(detail.case.dispute_id)
                      })
                    }
                  >
                    Seal
                  </button>
                </div>
              )}
            </div>

            <div className="space-y-2 text-sm">
              <table className="w-full text-xs [&_td]:px-2 [&_th]:px-2">
                <thead className="text-left text-slate-500"><tr><th></th><th>Option</th><th className="text-right">Expected value</th><th>Via</th></tr></thead>
                <tbody>
                  {a.options.map((o) => {
                    const off = !o.available || !!o.excluded_by
                    return (
                      <tr key={o.option} className={`border-t align-top ${off ? 'text-slate-400' : ''}`} title={o.basis}>
                        <td><input type="radio" name="opt" disabled={off} checked={option === o.option} onChange={() => choose(o.option)} /></td>
                        <td>
                          {LABEL[o.option]} {a.recommended === o.option && <span className="rounded bg-emerald-100 px-1 text-emerald-800">recommended</span>}
                          <div className="text-[11px]">{o.excluded_by ?? (o.available ? o.basis : 'PayPal does not allow this now')}</div>
                        </td>
                        <td className="text-right tabular-nums">{money(o.ev)}</td>
                        <td>{o.via.replace('_', ' ')}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              <textarea className="h-28 w-full rounded border border-slate-300 p-2 text-xs" value={note} onChange={(e) => setNote(e.target.value)} />
              <div className="flex flex-wrap items-center gap-2">
                <button className="rounded border border-slate-300 px-2 py-1 text-xs" disabled={busy} onClick={() => act(async () => setNote((await api.draftDispute(detail.case.dispute_id, option)).text))}>
                  Polish wording
                </button>
                <button
                  className="rounded bg-indigo-700 px-3 py-1 text-xs font-semibold text-white disabled:opacity-50"
                  disabled={busy || !chosen || !chosen.available || !!chosen.excluded_by || !note.trim()}
                  onClick={() =>
                    confirm(`Send "${LABEL[option]}" to PayPal for ${detail.case.dispute_id}? This cannot be undone.`) &&
                    act(async () => {
                      await api.respondDispute(detail.case.dispute_id, option, note)
                      setMsg('Sent to PayPal and recorded in the ledger.')
                      await load()
                      await open(detail.case.dispute_id)
                    })
                  }
                >
                  Send to PayPal
                </button>
                {option !== a.recommended && a.recommended && <span className="text-xs text-amber-700">You're overriding the recommendation. That's recorded.</span>}
                {!live && detail.case.status === 'WAITING_FOR_BUYER_RESPONSE' && (
                  <button className="rounded border border-slate-300 px-1 text-[11px]" disabled={busy} onClick={() => act(async () => { await api.simulateReturn(detail.case.dispute_id); await load(); await open(detail.case.dispute_id) })}>
                    Simulate: buyer ships the return
                  </button>
                )}
                {!live && detail.case.status !== 'RESOLVED' && (
                  <span className="ml-auto flex gap-1 text-[11px] text-slate-500">
                    Simulate PayPal's decision:
                    {[['RESOLVED_SELLER_FAVOUR', 'we win'], ['RESOLVED_BUYER_FAVOUR', 'buyer wins']].map(([code, label]) => (
                      <button key={code} className="rounded border border-slate-300 px-1" disabled={busy} onClick={() => act(async () => { await api.simulateResolve(detail.case.dispute_id, code); await load(); await open(detail.case.dispute_id) })}>{label}</button>
                    ))}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div>
            <div className="mb-1 text-xs font-semibold text-slate-600">Case timeline <span className="font-normal text-slate-400">(your local time)</span></div>
            <ol className="space-y-0.5 text-xs">
              {detail.timeline.map((e, i) => (
                <li key={i} className="flex gap-2">
                  <span className="w-40 shrink-0 tabular-nums text-slate-500">{when(e.at, e.who === 'deadline')}</span>
                  <span className={`w-16 shrink-0 rounded px-1 text-center ${WHO[e.who] ?? 'bg-slate-100'}`}>{e.who}</span>
                  <span>{e.what}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
      {msg && <p className="text-xs text-slate-700">{msg}</p>}
    </section>
  )
}
