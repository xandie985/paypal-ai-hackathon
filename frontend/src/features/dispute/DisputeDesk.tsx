import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, type DisputeDetail, type DisputeSummary, type RunSnapshot } from '../../api/client'
import { money, pct } from '../../lib/format'

const LABEL: Record<string, string> = {
  contest: 'Contest with sealed evidence',
  refund_with_return: 'Refund on return',
  accept: 'Accept and refund',
}
const err = (e: unknown) => (e instanceof ApiError ? e.message : String(e))

// Stage 8. The agent assesses; a human reads the draft and decides. Nothing reaches PayPal without "Send".
export function DisputeDesk({ run, live }: { run: RunSnapshot | null; live: boolean }) {
  const [list, setList] = useState<DisputeSummary[]>([])
  const [sel, setSel] = useState<string | null>(null)
  const [detail, setDetail] = useState<DisputeDetail | null>(null)
  const [option, setOption] = useState<string>('')
  const [note, setNote] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setList(await api.disputes())
    } catch (e) {
      setMsg(`Could not load disputes: ${err(e)}`)
    }
  }, [])
  useEffect(() => {
    load()
  }, [load])

  const open = async (id: string) => {
    setSel(id)
    setMsg(null)
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

  const run1 = async (fn: () => Promise<void>) => {
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
  const chosen = a?.options.find((o) => o.option === option)

  return (
    <section className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">8 · Dispute desk <span className="text-xs font-normal text-slate-500">PayPal disputes answered from the sealed ledger</span></h2>
        <div className="flex gap-2 text-xs">
          {!live && settled.length > 0 && (
            <select
              className="rounded border border-slate-300 px-2 py-1"
              value=""
              disabled={busy}
              onChange={(e) =>
                e.target.value &&
                run1(async () => {
                  const r = await api.simulateDispute(run!.run_id, e.target.value)
                  await load()
                  await open(r.dispute_id)
                })
              }
            >
              <option value="">Simulate a buyer dispute on…</option>
              {settled.map((i) => (
                <option key={i.lineage_id} value={i.lineage_id}>{i.title}</option>
              ))}
            </select>
          )}
          <button className="rounded border border-slate-300 px-2 py-1" onClick={load}>Refresh</button>
        </div>
      </header>

      {list.length === 0 ? (
        <p className="text-sm text-slate-500">No open disputes.</p>
      ) : (
        <table className="w-full text-sm [&_td]:px-2 [&_th]:px-2">
          <thead className="text-left text-xs text-slate-500">
            <tr><th>Case</th><th>Item</th><th className="text-right">Held</th><th>Stage</th><th>Days left</th><th>Evidence</th><th>Agent suggests</th></tr>
          </thead>
          <tbody>
            {list.map((d) => (
              <tr key={d.case.dispute_id} onClick={() => open(d.case.dispute_id)}
                className={`cursor-pointer border-t hover:bg-slate-50 ${sel === d.case.dispute_id ? 'bg-indigo-50' : ''}`}>
                <td className="font-mono text-xs">{d.case.dispute_id}</td>
                <td>{d.case.item_name}</td>
                <td className="text-right">{money(d.case.amount)}</td>
                <td className="text-xs">{d.case.stage} · {d.case.status.replaceAll('_', ' ').toLowerCase()}</td>
                <td>{d.days_left ?? '—'}</td>
                <td>{d.lineage_found ? <span className="text-emerald-700">sealed ✓</span> : <span className="text-rose-700">not found</span>}</td>
                <td>{d.recommended ? LABEL[d.recommended] : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {detail && a && (
        <div className="grid gap-4 border-t pt-3 lg:grid-cols-2">
          <div className="space-y-2 text-sm">
            <div className="font-semibold">{detail.case.reason.replaceAll('_', ' ').toLowerCase()}</div>
            <blockquote className="rounded bg-slate-50 p-2 text-xs italic text-slate-700">“{detail.case.buyer_note}”</blockquote>
            <ul className="space-y-0.5 text-xs">
              {!a.facts.lineage_found && <li className="text-rose-700">No sealed record matches this payment. The agent won't contest without evidence.</li>}
              {a.facts.lineage_found && (
                <>
                  <li>Order <b className="font-mono">{String(a.facts.order_id)}</b> sealed {String(a.facts.purchased_on)} ({String(a.facts.days_since_purchase)} days ago)</li>
                  <li>Return window: {a.facts.sealed_return_days == null ? 'hidden by the merchant' : `${a.facts.sealed_return_days} days`}{a.facts.within_return_window ? ' · still open' : ''}</li>
                  <li>Human approved before payment: {a.facts.human_approved ? 'yes' : 'no'} · ledger chain {a.facts.chain_ok ? 'intact' : 'BROKEN'}</li>
                  <li>Missing evidence: {(a.facts.missing_evidence as string[]).join(', ') || 'none'}</li>
                </>
              )}
              <li>Buyer's claim reads as: <b>{a.facts.claim.replace('_', ' ')}</b> · win odds {pct(a.win_odds * 100, 0)}</li>
            </ul>
            {a.facts.lineage_found && (
              <a className="text-xs text-indigo-700 hover:underline" href={api.briefUrl(detail.case.dispute_id)}>Download evidence brief (PDF)</a>
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
              <button className="rounded border border-slate-300 px-2 py-1 text-xs" disabled={busy}
                onClick={() => run1(async () => setNote((await api.draftDispute(detail.case.dispute_id, option)).text))}>
                Polish wording
              </button>
              <button
                className="rounded bg-indigo-700 px-3 py-1 text-xs font-semibold text-white disabled:opacity-50"
                disabled={busy || !chosen || !chosen.available || !!chosen.excluded_by || !note.trim()}
                onClick={() =>
                  confirm(`Send "${LABEL[option]}" to PayPal for ${detail.case.dispute_id}? This cannot be undone.`) &&
                  run1(async () => {
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
            </div>
          </div>
        </div>
      )}
      {msg && <p className="text-xs text-slate-700">{msg}</p>}
    </section>
  )
}
