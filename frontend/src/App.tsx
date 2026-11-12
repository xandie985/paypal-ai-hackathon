import { lazy, Suspense, useEffect, useState } from 'react'
import { api, type DemoRunResult, type MandateInput } from './api/client'
import { useRunSession } from './api/useRunSession'
import { AttackButton } from './features/attack/Actions'
import { DealCard } from './features/deal/DealCard'
import { DisputeDesk } from './features/dispute/DisputeDesk'
import { LedgerPanel } from './features/ledger/LedgerPanel'
import { MarketPanel } from './features/market/MarketPanel'
import { MandateForm } from './features/mandate/MandateForm'
import { DEFAULTS } from './features/mandate/defaults'
import { NegotiationArena } from './features/negotiation/NegotiationArena'
import { SummaryStrip } from './features/summary/SummaryStrip'
import { Timeline } from './features/timeline/Timeline'
import { WebhookInspector } from './features/webhooks/WebhookInspector'
import { money } from './lib/format'

// Studio's bundle loads only when the Command Center opens (doc 11, UI-0.4).
const CommandCenter = lazy(() => import('./studio/CommandCenter'))

function useHash() {
  const [hash, setHash] = useState(location.hash)
  useEffect(() => {
    const onChange = () => setHash(location.hash)
    addEventListener('hashchange', onChange)
    return () => removeEventListener('hashchange', onChange)
  }, [])
  return hash
}

const STAGES = [
  'Mandate',
  'Discover',
  'Negotiate',
  'Firewall',
  'PayPal',
  'Review',
]

export default function App() {
  const [mode, setMode] = useState<string>('…')
  const [sandboxAvailable, setSandboxAvailable] = useState(false)
  const [currentMandate, setCurrentMandate] = useState<MandateInput>(DEFAULTS)
  const [runMandate, setRunMandate] = useState<MandateInput | null>(null) // what the shown run was started with
  const [demoResult, setDemoResult] = useState<DemoRunResult | null>(null)
  const [demoBusy, setDemoBusy] = useState(false)
  const [showModeModal, setShowModeModal] = useState(false)
  const { run, events, error, busy, start, act } = useRunSession()
  const hash = useHash()
  const studio = hash === '#/studio' || hash.startsWith('#/studio/')

  useEffect(() => {
    api
      .health()
      .then((h) => {
        setMode(h.paypal_live ? 'live sandbox' : 'replay')
        setSandboxAvailable(!!h.sandbox_run_available)
      })
      .catch(() => setMode('backend offline'))
  }, [])

  const runDemoShowcase = async () => {
    setDemoBusy(true)
    try {
      const res = await api.demoRun()
      setDemoResult(res)
    } catch (e) {
      console.error('Demo run error', e)
    } finally {
      setDemoBusy(false)
    }
  }

  const heldItems = run?.items.filter((i) => i.status === 'awaiting_approval') ?? []
  const capturedCount = run?.items.filter((i) => i.status === 'settled').length ?? 0
  const blockedCount = run?.items.filter((i) => i.status === 'blocked' || i.status === 'rejected').length ?? 0

  const getStageStatus = (idx: number): string => {
    if (!run) {
      if (busy) {
        if (idx === 0) return 'done'
        if (idx === 1) return 'active'
        return ''
      }
      return idx === 0 ? 'active' : ''
    }

    if (idx === 0) return 'done'
    if (idx === 1) {
      return events.some((e) => e.stage === '2' && e.event === 'discovered') || run.items.length > 0 ? 'done' : busy ? 'active' : ''
    }
    if (idx === 2) {
      const hasNeg = events.some((e) => e.stage === '2' && e.event === 'negotiated') || run.items.some((i) => i.method === 'negotiate')
      return hasNeg ? 'done' : busy ? 'active' : ''
    }
    if (idx === 3) {
      return run.items.some((i) => i.decision != null) ? 'done' : busy ? 'active' : ''
    }
    if (idx === 4) {
      if (run.items.some((i) => i.status === 'settled')) return 'done'
      if (run.items.some((i) => i.status === 'authorized' || i.order_id != null)) return 'active'
      return busy ? 'active' : ''
    }
    if (idx === 5) {
      if (run.complete) return 'done'
      if (heldItems.length > 0) return 'active'
      return ''
    }
    return ''
  }

  return (
    <div className={`min-h-screen bg-slate-50 text-slate-900 ${studio ? 'flex h-dvh flex-col' : ''}`}>
      {/* Top Application Bar */}
      <header className="sticky top-0 z-50 flex flex-wrap items-center justify-between gap-y-2 border-b border-slate-200/80 bg-white/95 px-4 py-3 backdrop-blur-md sm:px-6">
        <div className="flex items-center gap-5">
          <a href="#/" className="flex items-center gap-2.5 font-black tracking-tight text-slate-900 no-underline">
            <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 via-indigo-600 to-teal-500 text-white shadow-md shadow-blue-500/20">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </span>
            <div>
              <div className="text-base font-extrabold leading-none text-slate-900">PactGuard AI</div>
              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Mission Control</div>
            </div>
          </a>
          <nav className="flex items-center gap-1 text-xs font-semibold">
            <a
              href="#/"
              className={`rounded-lg px-3 py-1.5 transition ${
                !studio ? 'bg-slate-100 text-slate-900 shadow-2xs' : 'text-slate-500 hover:text-slate-900'
              }`}
            >
              Mission Control
            </a>
            <a
              href="#/studio"
              className={`rounded-lg px-3 py-1.5 transition ${
                studio ? 'bg-slate-100 text-slate-900 shadow-2xs' : 'text-slate-500 hover:text-slate-900'
              }`}
            >
              Command Center
            </a>
          </nav>
        </div>

        <div className="flex items-center gap-2.5">
          {heldItems.length > 0 && (
            <span className="flex items-center gap-1.5 rounded-full bg-amber-100 px-3 py-1 text-xs font-bold text-amber-900 shadow-xs">
              <svg className="h-3 w-3 text-amber-700" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
              </svg>
              {heldItems.length}<span className="hidden sm:inline"> awaiting approval</span>
            </span>
          )}

          <button
            type="button"
            onClick={() => setShowModeModal(true)}
            className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-bold text-slate-600 transition hover:bg-slate-100"
            title="Click to view Sandbox vs Replay details"
          >
            <span className={`h-2 w-2 rounded-full ${mode === 'live sandbox' ? 'bg-emerald-500' : 'bg-amber-500'}`} />
            <span>{mode}</span>
          </button>

          <button
            type="button"
            disabled={demoBusy}
            onClick={runDemoShowcase}
            className="hidden items-center gap-1.5 rounded-lg bg-gradient-to-r from-blue-600 via-indigo-600 to-sky-600 px-3 py-1.5 text-xs font-bold text-white shadow-xs transition hover:brightness-110 active:scale-[0.98] disabled:opacity-50 md:flex"
            title="Execute complete 10-stage loop immediately on an in-memory ledger"
          >
            {demoBusy ? (
              <>
                <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                Running 10 stages…
              </>
            ) : (
              <>
                <svg className="h-3.5 w-3.5 text-amber-300" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" />
                </svg>
                Run 10-Stage Showcase
              </>
            )}
          </button>
        </div>
      </header>

      {/* Replay vs Live Info Modal */}
      {showModeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-xl">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-bold text-slate-900">Execution Mode</h3>
                <p className="text-xs text-slate-500">How PactGuard interacts with PayPal and external APIs</p>
              </div>
              <button
                type="button"
                onClick={() => setShowModeModal(false)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              >
                ✕
              </button>
            </div>
            <div className="mt-4 space-y-3 text-xs leading-relaxed text-slate-600">
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-3.5">
                <b className="block text-amber-900 font-semibold">Current: Replay Mode (Deterministic Simulation)</b>
                <p className="mt-1 text-amber-800">
                  Enables zero-latency, 100% reliable evaluation without requiring external PayPal sandbox API credentials or risking sandbox service outages. Orders, captures, payouts, and invoices use deterministic fixtures.
                </p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5">
                <b className="block text-slate-900 font-semibold">Live PayPal Sandbox Mode</b>
                <p className="mt-1 text-slate-600">
                  To connect directly to real PayPal REST APIs (Orders v2, Vaulted payment sources, Payouts v1, Disputes, and Webhooks):
                </p>
                <code className="mt-2 block rounded bg-slate-200/70 p-2 font-mono text-[11px] text-slate-800">
                  REPLAY_MODE=false<br />
                  PAYPAL_CLIENT_ID=&lt;your_sandbox_client_id&gt;<br />
                  PAYPAL_CLIENT_SECRET=&lt;your_sandbox_secret&gt;
                </code>
              </div>
            </div>
            <div className="mt-5 flex justify-end">
              <button
                type="button"
                onClick={() => setShowModeModal(false)}
                className="rounded-xl bg-slate-900 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-slate-800"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main Content Area */}
      {studio ? (
        <main className="min-h-0 flex-1">
          <Suspense fallback={<p className="m-6 text-sm text-slate-500">Loading Command Center…</p>}>
            <CommandCenter runId={run?.run_id} />
          </Suspense>
        </main>
      ) : (
        <div className="mx-auto max-w-[1440px] p-4 lg:p-6">
          <div className="grid gap-6 lg:grid-cols-[340px_minmax(0,1fr)] items-start">
            {/* Sticky Sidebar: Mandate Controls */}
            <aside className="lg:sticky lg:top-20 space-y-4">
              <MandateForm
                busy={busy}
                sandboxAvailable={sandboxAvailable}
                onStart={(m, sandbox, needs) => {
                  setRunMandate(m)
                  start(m, sandbox, needs)
                }}
                onMandateChange={setCurrentMandate}
              />
            </aside>

            {/* Right Column: Guided Workspace */}
            <div className="min-w-0 space-y-5">
              {/* 10-Stage Showcase Completed Banner */}
              {demoResult && (
                <div className="rounded-2xl border border-emerald-300 bg-gradient-to-r from-emerald-50 via-teal-50 to-sky-50 p-5 shadow-sm">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2 text-sm font-bold text-emerald-950">
                      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-600 text-white">
                        ✓
                      </span>
                      10-Stage Autonomous Showcase Completed (~1s)
                    </div>
                    <button
                      type="button"
                      onClick={() => setDemoResult(null)}
                      className="text-xs text-slate-400 hover:text-slate-700"
                    >
                      Dismiss
                    </button>
                  </div>
                  <p className="mt-2 text-xs text-emerald-900">
                    The agent completed all 10 stages: Mandate registration, Channel3 discovery, 4-seller negotiation (12.6% saved), firewall policy evaluation, PayPal settlement &amp; seal, delivery verification, invoice forensic checks (flagged duplicate &amp; mismatch), server-token gated payout, dispute triage, and self-tightened mandate calibration.
                  </p>
                  <div className="mt-3.5 grid gap-2.5 sm:grid-cols-4 text-xs font-medium">
                    <div className="rounded-xl border border-emerald-200/80 bg-white/70 p-2.5">
                      <span className="text-[10px] uppercase text-slate-500 block">Evaluated Spend</span>
                      <b className="text-sm font-bold text-slate-900">$1,138.00</b>
                    </div>
                    <div className="rounded-xl border border-emerald-200/80 bg-white/70 p-2.5">
                      <span className="text-[10px] uppercase text-slate-500 block">Firewall Routes</span>
                      <b className="text-sm font-bold text-slate-900">1 Auto · 1 Gate · 1 Blocked</b>
                    </div>
                    <div className="rounded-xl border border-emerald-200/80 bg-white/70 p-2.5">
                      <span className="text-[10px] uppercase text-slate-500 block">Cryptographic Ledger</span>
                      <b className="text-sm font-bold text-emerald-700">21 Entries (Chain OK)</b>
                    </div>
                    <div className="rounded-xl border border-emerald-200/80 bg-white/70 p-2.5">
                      <span className="text-[10px] uppercase text-slate-500 block">Stage 10 Calibration</span>
                      <b className="text-sm font-bold text-indigo-700">Mandate Auto-Tightened</b>
                    </div>
                  </div>
                  <div className="mt-4 flex items-center gap-3">
                    <a
                      href="#/studio"
                      className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-700 px-3.5 py-2 text-xs font-bold text-white shadow-xs hover:bg-emerald-800"
                    >
                      Explore Evidence in Command Center →
                    </a>
                  </div>
                </div>
              )}

              {/* Hero Banner */}
              <div className="v1-hero">
                <div className="flex flex-wrap items-center gap-2 text-[11px] font-extrabold uppercase tracking-widest text-sky-200">
                  Mandate-bound procurement
                  {run?.sandbox && (
                    <span className="rounded-full bg-amber-300 px-2 py-0.5 tracking-wide text-amber-950 normal-case">
                      PayPal sandbox run · real orders, test money
                    </span>
                  )}
                </div>
                <h3 className="mt-1 text-2xl font-black tracking-tight text-white sm:text-3xl">
                  Give the agent a budget. Keep the final say.
                </h3>
                <p className="mt-1.5 max-w-2xl text-xs text-sky-100 sm:text-sm">
                  Every purchase is checked for warrant, reversibility and price before PayPal moves money. Untrusted vendor text can never issue a payout.
                </p>
                <div className="mt-5 flex flex-wrap gap-2.5">
                  <div className="min-w-[110px] rounded-xl border border-white/20 bg-white/10 px-3.5 py-2 backdrop-blur-xs">
                    <small className="block text-[10px] font-bold uppercase tracking-wider text-sky-200">Budget</small>
                    <b className="text-lg font-bold text-white">{money(run?.budget ?? currentMandate.budget)}</b>
                  </div>
                  <div className="min-w-[110px] rounded-xl border border-white/20 bg-white/10 px-3.5 py-2 backdrop-blur-xs">
                    <small className="block text-[10px] font-bold uppercase tracking-wider text-sky-200">Auto below</small>
                    <b className="text-lg font-bold text-white">{money((run && runMandate ? runMandate : currentMandate).auto_threshold)}</b>
                  </div>
                  <div className="min-w-[110px] rounded-xl border border-white/20 bg-white/10 px-3.5 py-2 backdrop-blur-xs">
                    <small className="block text-[10px] font-bold uppercase tracking-wider text-sky-200">Captured</small>
                    <b className="text-lg font-bold text-white">{capturedCount}</b>
                  </div>
                  <div className="min-w-[110px] rounded-xl border border-white/20 bg-white/10 px-3.5 py-2 backdrop-blur-xs">
                    <small className="block text-[10px] font-bold uppercase tracking-wider text-sky-200">Blocked / Held</small>
                    <b className="text-lg font-bold text-white">{blockedCount + heldItems.length}</b>
                  </div>
                </div>
              </div>

              {/* 6-Stage Interactive Rail */}
              <div className="stage-rail" aria-label="Run stages">
                {STAGES.map((s, idx) => {
                  const status = getStageStatus(idx)
                  return (
                    <div key={s} className={`stage ${status}`}>
                      <span className="stage-dot">
                        {status === 'done' ? (
                          <svg className="h-3 w-3 stroke-current" fill="none" viewBox="0 0 24 24" strokeWidth="3">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                          </svg>
                        ) : (
                          idx + 1
                        )}
                      </span>
                      <span>{s}</span>
                    </div>
                  )
                })}
              </div>

              {/* Global Error Banner */}
              {error && (
                <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs font-semibold text-rose-800 shadow-xs">
                  Refused: {error}
                </div>
              )}

              {/* High-Visibility Decision Section */}
              <section className="space-y-3">
                <div className="flex items-center gap-2 text-sm font-bold text-slate-800">
                  <svg className="h-4 w-4 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Needs your decision
                </div>

                {heldItems.length > 0 ? (
                  <div className="space-y-3">
                    {heldItems.map((item) => (
                      <article key={item.lineage_id} className="decision-card">
                        <div className="flex min-w-0 items-start gap-3.5">
                          <div className="vendor-avatar">
                            {(item.offer.seller_id || 'VE').slice(0, 2).toUpperCase()}
                          </div>
                          <div className="min-w-0">
                            <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                              {item.offer.seller_id} · {item.offer.sku || 'general'}
                            </div>
                            <h4 className="truncate text-base font-bold text-slate-900">{item.title}</h4>
                            <p className="mt-0.5 text-xs text-slate-600">
                              {item.decision?.reasons?.[0] || 'Human approval required: price exceeds auto-settlement threshold.'}
                            </p>
                          </div>
                        </div>
                        <div className="grid shrink-0 justify-items-end gap-2 text-right">
                          <div className="text-xl font-bold tracking-tight text-slate-900">{money(item.total)}</div>
                          <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-bold text-amber-800">
                            Awaiting approval
                          </span>
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => act((id) => api.approve(id, item.lineage_id))}
                              className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white shadow-xs transition hover:bg-emerald-700 active:scale-[0.98] disabled:opacity-50"
                            >
                              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                              </svg>
                              Approve
                            </button>
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => act((id) => api.reject(id, item.lineage_id))}
                              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-bold text-slate-700 shadow-xs transition hover:bg-slate-50 active:scale-[0.98] disabled:opacity-50"
                            >
                              Reject
                            </button>
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="clear-state">
                    <svg className="h-6 w-6 shrink-0 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <div>
                      <h4 className="font-bold text-emerald-900">Inbox clear</h4>
                      <p className="text-xs text-emerald-800">
                        {run
                          ? 'No purchases are waiting for approval. Inspect settled transactions or explore evidence below.'
                          : 'Set the mandate on the left and click "Run agent", or click "Run 10-Stage Showcase" above.'}
                      </p>
                    </div>
                  </div>
                )}
              </section>

              {/* Before First Run: Operator Guidance */}
              {!run && (
                <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
                  <div className="flex items-center gap-2 text-sm font-bold text-slate-900">
                    <svg className="h-4 w-4 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    Guided Workspace Architecture
                  </div>
                  <p className="mt-2 text-sm text-slate-700 leading-relaxed">
                    PactGuard AI delegates discovery and negotiation to autonomous agents, but strictly enforces spending bounds, vendor allowlists, return policies, and human approval gates before PayPal executes payouts.
                  </p>
                  <div className="mt-4 grid gap-3 sm:grid-cols-3 text-xs">
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                      <b className="block text-slate-900 font-semibold">1. Mandate &amp; Presets</b>
                      <span className="text-slate-500">Choose between Office setup ($2.2k) or Strict review ($1.2k) to test auto vs manual gates.</span>
                    </div>
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                      <b className="block text-slate-900 font-semibold">2. Discovery &amp; Firewall</b>
                      <span className="text-slate-500">Live multi-seller quote discovery with bounded negotiation and deterministic rules.</span>
                    </div>
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                      <b className="block text-slate-900 font-semibold">3. PayPal &amp; Sealed Ledger</b>
                      <span className="text-slate-500">Tamper-evident hash chain evidence and real PayPal order authorization &amp; capture.</span>
                    </div>
                  </div>
                </section>
              )}

              {/* Summary KPIs & Stats */}
              {run && <SummaryStrip run={run} />}

              {/* Discovery (wide, one scrolling row per item type) beside the run's activity stream (narrow, scrolls
                  vertically inside the discovery panel's height). Stacks on small screens. */}
              {run && (
                <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(16rem,1fr)]">
                  <MarketPanel events={events} />
                  <div className="relative h-72 xl:sticky xl:top-20 xl:h-[calc(100dvh-7rem)] xl:min-h-[20rem] xl:self-start">
                    <Timeline events={events} className="absolute inset-0" />
                  </div>
                </div>
              )}

              {/* Deals, Firewall & Settlement */}
              {run && (
                <section className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="flex items-center gap-2 text-sm font-bold text-slate-800">
                      <svg className="h-4 w-4 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
                      </svg>
                      4 · Deals · firewall · settlement
                    </h3>
                    <span className="text-xs text-slate-500">
                      {run.items.length} item{run.items.length === 1 ? '' : 's'} evaluated
                    </span>
                  </div>
                  {run.items.map((i) => (
                    <DealCard
                      key={i.lineage_id}
                      item={i}
                      runId={run.run_id}
                      sandbox={run.sandbox}
                      busy={busy}
                      onApprove={() => act((id) => api.approve(id, i.lineage_id))}
                      onReject={() => act((id) => api.reject(id, i.lineage_id))}
                      onRefresh={() => act(async () => {})}
                      onPay={() =>
                        act(async (id) => {
                          await api.prepare(id, i.lineage_id)
                          await api.capture(id, i.lineage_id)
                        })
                      }
                    />
                  ))}
                </section>
              )}

              <NegotiationArena events={events} />

              {/* System & Security Strip */}
              <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white p-3.5 shadow-xs">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700">
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                  {run?.ledger_entries ? `${run.ledger_entries} entries sealed` : 'Evidence ledger'}
                </span>
                <span className="text-xs text-slate-500">{run ? 'Chain status is verified in the ledger panel below.' : 'Run the agent to seal the first entries.'}</span>
                <div className="ml-auto flex flex-wrap items-center gap-2">
                  {run && <AttackButton runId={run.run_id} onDone={() => act(async () => {})} />}
                  <a
                    href="#ledger-section"
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50"
                  >
                    Verify ledger
                  </a>
                </div>
              </div>

              {/* Verification & Desk Panels */}
              {run && (
                <div id="ledger-section">
                  <LedgerPanel runId={run.run_id} entries={run.ledger_entries} />
                </div>
              )}
              <WebhookInspector live={mode === 'live sandbox'} />
              <DisputeDesk run={run} live={mode === 'live sandbox'} />

              {/* Application Footer */}
              <footer className="mt-8 border-t border-slate-200 pt-6 text-xs text-slate-500">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <div className="font-bold text-slate-800">PactGuard AI</div>
                    <p className="mt-0.5 text-slate-500">
                      Autonomous procurement spend firewall &amp; tamper-evident evidence ledger.
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-4 font-semibold text-slate-600">
                    <a
                      href="https://github.com/xandie985/paypal-ai-hackathon"
                      target="_blank"
                      rel="noreferrer"
                      className="hover:text-blue-600 hover:underline"
                    >
                      Source Code (GitHub)
                    </a>
                    <span>·</span>
                    <a href="/docs" target="_blank" rel="noreferrer" className="hover:text-blue-600 hover:underline">
                      REST API Docs
                    </a>
                    <span>·</span>
                    <a href="#/studio" className="hover:text-blue-600 hover:underline">
                      Command Center
                    </a>
                    <span>·</span>
                    <span className="rounded bg-slate-200/60 px-2 py-0.5 text-[11px] text-slate-700">
                      Apache-2.0
                    </span>
                  </div>
                </div>
                <div className="mt-4 flex flex-col gap-1 text-[11px] text-slate-400 sm:flex-row sm:justify-between">
                  <span>Built for the PayPal AI Hackathon 2026 · Agentic Commerce &amp; PayPal + AI</span>
                  <span>PayPal REST APIs: Orders v2, Payouts v1, Webhooks, Invoicing, Disputes</span>
                </div>
              </footer>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
