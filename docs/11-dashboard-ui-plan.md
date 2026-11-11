# Section 11: Dashboard & UI Plan

This document is the reference for all UI and dashboard work on PactGuard AI. It covers:

1. **Approach.** How UI work runs alongside the build phases in [doc 10](10-execution-plan.md), and why we don't build a throwaway baseline now and redo it at the end.
2. **Design system.** Tokens, colour meanings, type and motion. Every UI task uses them.
3. **Screens.** Mission Control (the live agent run), the Command Center (AG Studio) and the Disputes desk.
4. **AG Studio reference.** What we checked in the AG Studio 3.0.0 docs and the PayPal boilerplate, and what we still need to check.
5. **Phase plan.** UI tasks with IDs for each phase, plus a tracker that later sessions update.

> **As of:** Sunday 2026-11-01. **Deadline:** Thursday 2026-11-12, 12:00 PM PST. We submit on **Wed Nov 11**. Feature freeze is **Tue Nov 10, 18:00**.

---

## 0. How to use this document

For any UI or dashboard task:

1. Find the task ID in the tracker (§12). Read its row in the phase plan (§11).
2. Build with the tokens and primitives in §4. Don't add raw Tailwind palette classes such as `bg-slate-50` in new code.
3. Before relying on an AG Studio API, check §6. Anything marked **(verify)** was not confirmed in the docs. Check it against the installed package first.
4. Meet the definition of done in §13.
5. Update the task's status in §12 in the same change.

---

## 1. Approach: baseline now or polish now?

**Neither extreme.** Build the foundation once, now. Build each screen in its final form when its data arrives. Finish with a polish sweep, not a rebuild.

| Option | Cost | Problem |
|---|---|---|
| Baseline now, full UI rework at the end | Low now, high later | The rework lands in Phases 4–5, where the time is already booked for deploy, evaluation and the video. Every screen gets built twice. |
| Full polish now | High now | Data shapes are still moving: seeded history in Phase 2, disputes and payouts in Phase 3. Polishing a screen whose data will change wastes the effort. |
| **Foundation now, final form per phase, polish sweep at the end** | ~½ day now, then a share of each phase | None worth noting. Later screens inherit the tokens, shell and Studio theme, so the final pass covers states, accessibility, motion and copy instead of layout. |

The UI work has three layers:

| Layer | When | What | Rule |
|---|---|---|---|
| **L0 Foundation** | Now (Nov 1–2) | Tokens, dark mode, app shell, primitives, AG Studio spike | Done once. Everything later builds on it. |
| **L1 Screens** | With each phase | Each screen built in its final layout as its endpoints land | No placeholder screens. If the data isn't ready, use replay data. |
| **L2 Polish sweep** | Phase 4 (Nov 9–10) | Empty, loading and error states, accessibility, responsiveness, performance, copy, honesty labels | No new layouts. Only finishing work. |

The existing Phase 1 components count as the baseline. UI-0 moves them onto the primitives, which is a mechanical change. UI-1 then redesigns them in place.

---

## 2. What we are optimising for

### 2.1 Best Use of AG Studio ($5,000 for 1st)

The AG Grid prize page says the award covers both how the dashboard looks and how it was built. It names two things:

- **Polish:** custom widgets, theming and layout tools, "not just AG Grid or AG Charts on their own".
- **Studio Agent Framework:** a custom agent that talks to Studio's built-in agents, or a swapped-in harness.

The AG team published no detailed rubric. The table below is our reading of what they value, based on their blog posts (sources in §15).

| What they value | Source | Our answer | Where |
|---|---|---|---|
| Custom widgets that aren't stock charts, fully wired: data, display states, cross-filter, AI-operable | 88-second blog post, custom widgets docs | Mandate Ruler, Savings Dumbbell, Lineage Chain (W1–W3), plus Firewall Flow (W4) | §9, UI-2.5 |
| One theme across Studio, our own UI and the widgets, in light and dark | Theming docs, Figma design system post | `--pg-*` tokens drive Tailwind, `studioTheme`, AG Grid, and the CSS in our custom widgets | §4.5, UI-0.1, UI-2.4 |
| Deliberate layout: a curated multi-page report, plus view and edit modes | "Grids + Charts != Dashboards" post | Five-page curated `initialState`, Present/Edit toggle, reset to curated | §5.3, UI-2.3 |
| Coverage of AG's checklist: global filters, cross-filtering, saved state, calculated fields, undo/redo, dark mode, keyboard | "Grids + Charts != Dashboards" post | Each item ticked in the polish checklist | §13.2 |
| A custom agent that talks to the built-in agents | Hackathon prize page, Agent Framework post | **PactGuard Copilot** (our primary agent) delegates to the built-in Planning, Page, Widget and Data agents, and to our own Auditor | §10, UI-2.7 |
| Guardrails set by which tools an agent has, not by prompts | Agent Framework post | Studio agents get no money tools. The FastAPI proxy also refuses any tool not on an allowlist. | §10.4 |
| Agents as real users of the dashboard | Launch Week post, WebMCP post | The Sentinel agent builds an Incidents page when an attack is blocked. WebMCP read-only tools are a stretch goal. | UI-2.10, UI-2.12 |
| Real payments data in a multi-table model | Boilerplate, hackathon post | Transactions, factors, offers, ledger and suppliers, with relationships between them | §8 |

### 2.2 Grand Prize, Agentic Commerce, PayPal + AI

These judges watch the **run**, not the dashboard. Mission Control has to make the agent's governance visible and easy to follow: the auto-purchase line, the firewall's four factors, the human pause, the real PayPal order, and the sealed evidence. Doc 08's demo beats map onto screens like this:

| Demo beat (doc 08 / doc 10 Phase 5) | Screen | Key UI moment |
|---|---|---|
| Hook (Issue #95) | Mission Control | Mandate card with the Mandate Ruler: the line the agent may not cross |
| Discovery and negotiation | Mission Control | Market cards, then the race lanes converging below the baseline line |
| Firewall: auto, approval, attack | Mission Control | The Firewall Checkpoint drawer. The four gates light up in sequence and the stopwatch shows under 1 ms. The attack gets a BLOCKED stamp. |
| PayPal settle | Mission Control | PayPal button in the drawer, then the Decide-and-Prove receipt |
| Dispute defended from the seal | Disputes desk | Dispute card: win odds, sealed terms hash, "chain verified" |
| AG Studio | Command Center | The Copilot builds a widget live, then a click on the Ruler cross-filters everything |

---

## 3. Where the UI stands

Audited on 2026-11-01 against commit `59e0884`.

| Area | State | Gap |
|---|---|---|
| Stack | React 19.3, Vite 8, Tailwind 4.3, TS 7. No UI libraries. | Studio 3.0 needs TS ≥ 5.8.3, which TS 7 satisfies. React 17–19+ is supported. |
| Shell | One centred column (`max-w-5xl`). The header shows the replay/live mode. Title "frontend", default favicon. | No navigation, brand, theme or status area |
| Styling | Hard-coded Tailwind palette classes (slate, indigo, emerald, amber, rose) in every component | No tokens and no dark mode. Colour meanings are repeated in each file. |
| Components | `MandateForm`, `SummaryStrip`, `MarketPanel`, `NegotiationArena`, `DealCard` + `RouteCard`, `PayPalApprove` (replay only), `AttackButton`, `RetryButton`, `LedgerPanel`, `Timeline` | They work and cover Phase 1, but they're dense tables. There's no visual story, no motion, and no drawer for the approval moment. |
| Data plumbing | `useRunSession` handles SSE, the snapshot and the 409 guard | Good. Keep it. |
| AG Studio | Installed (3.0.0) and licensed. B-6 closed on 2026-11-01. `#/studio` is a lazy route over `/api/studio/rows` (UI-0.4). | The spike is done. Next comes the data contract (§8) and the full theme (UI-2.4). |
| Studio data | `GET /api/studio/rows` returns one flat table plus KPIs, with `created_at` / `updated_at` (newest first), `source` (run or seeded) and a frozen column contract (`s09_observe.ROW_COLUMNS`). `?history=true` adds ~60 seeded purchases over 28 days. | The multi-table model (§8, `GET /api/studio/sources`) is still to do |
| AI | `integrations/llm.py` (Claude) exists on the backend. No browser-facing AI route. | We need a Claude adapter and a FastAPI proxy (§10) |

> **Update (2026-11-12).** This table is the 2026-11-01 audit, kept as written. Since then: the Command Center is a six-page report (Purchases, Agent Activity, Revenue, Receivables, Cash, Catalogue) with host-drawn grouped tabs, a hash-synced selected page, a Live/Replay chip with Refresh, loading and error states, and two detail drawers (lineage and PayPal) joined on `capture_id`. The Claude adapter and `app/ai_proxy.py` exist, and the Studio assistant runs on Claude Haiku 5.5. The Studio theme is in `src/studio/theme.ts`; the `src/ui/` primitives of §4.6 were not created. The multi-table model of §8 was not built as specified; the agent's data is one flat `Transactions` table, joined to PayPal account tables.

---

## 4. Design system

### 4.1 Principles

1. **Colour means route.** Green means auto-settle, amber means needs approval, red means blocked. These colours appear nowhere else, so nobody reads green as "good" by accident.
2. **Evidence looks like evidence.** Hashes, lineage IDs and seals use the mono font and the violet evidence colour. They can always be copied.
3. **Money is exact and aligned.** Every amount uses `tabular-nums` and the `Money` primitive. No rounding in the display.
4. **Honest by default.** Simulated sellers, seeded history, illustrative fees and replay mode each carry a visible label (doc 10 §2.3, rule 5).
5. **Motion explains, never decorates.** It runs 150–300 ms and is used only for state changes (a gate passing, a seal stamping, a stage lighting up). `prefers-reduced-motion` turns it off.

### 4.2 Tokens

The tokens are defined once as CSS variables in `frontend/src/index.css`. Dark values apply under `[data-theme="dark"]` on `<html>`.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--pg-bg` | `#F5F7FB` | `#0A0F1C` | Page canvas |
| `--pg-surface` | `#FFFFFF` | `#111827` | Cards, drawers, widgets |
| `--pg-surface-2` | `#EEF1F7` | `#18213A` | Insets, table headers, code blocks |
| `--pg-border` | `#E1E6EF` | `#26314B` | Dividers, card borders |
| `--pg-ink` | `#0B1220` | `#E7EBF3` | Primary text |
| `--pg-ink-2` | `#4A5568` | `#A6B0C3` | Secondary text |
| `--pg-ink-3` | `#8A94A6` | `#6E7A91` | Captions, disabled |
| `--pg-primary` | `#0070E0` | `#4D9BFF` | Primary actions, links, focus ring |
| `--pg-primary-ink` | `#FFFFFF` | `#06111F` | Text on primary |
| `--pg-evidence` | `#6D5BD0` | `#A397FF` | Hashes, seals, ledger, lineage |
| `--pg-auto` / `--pg-auto-soft` | `#0F9D6E` / `#E3F6EE` | `#34D399` / `#0E2A22` | AUTO_SETTLE |
| `--pg-human` / `--pg-human-soft` | `#C77800` / `#FFF3DC` | `#FBBF24` / `#2E2410` | HUMAN_APPROVAL |
| `--pg-blocked` / `--pg-blocked-soft` | `#D93654` / `#FDE7EB` | `#FB7185` / `#33141C` | BLOCKED, guard refusals |
| `--pg-live` | `#0EA5E9` | `#38BDF8` | "Live sandbox" badge, streaming dot |
| `--pg-sim` | `#8A94A6` | `#6E7A91` | "Simulated" / "seeded" / "illustrative" labels |
| `--pg-chart-1..8` | `#0070E0 #6D5BD0 #14B8A6 #F59E0B #EC4899 #64748B #84CC16 #F97316` | Same hues, 15% lighter | Categorical chart palette. It deliberately avoids the route colours. |
| `--pg-radius` / `--pg-radius-sm` | `12px` / `8px` | — | Cards / controls |
| `--pg-shadow` | `0 1px 2px rgb(11 18 32 / .06), 0 4px 16px rgb(11 18 32 / .06)` | `0 0 0 1px var(--pg-border)` | Raised surfaces |

Check every token pair against WCAG AA contrast (4.5:1 for text) in UI-4.2. The soft route colours are backgrounds only. Text on them uses the strong colour.

### 4.3 Colour meanings

| Meaning | Token | Shows up as |
|---|---|---|
| Auto-settle | `--pg-auto` | Route chip, Ruler zone ≤ auto threshold, gate pass tick |
| Needs approval | `--pg-human` | Route chip, Ruler zone between threshold and cap, approval drawer accent |
| Blocked | `--pg-blocked` | Route chip, Ruler zone above cap, BLOCKED stamp, 409 guard banner, attack mode border |
| Evidence | `--pg-evidence` | `Hash` primitive, seal receipt, Lineage Chain links, "chain verified" badge |
| Live | `--pg-live` | Header "LIVE SANDBOX" badge, SSE streaming dot |
| Simulated | `--pg-sim` | "simulated seller", "seeded history", "illustrative fee", "REPLAY" |

**Route labels are fixed wording:** "Auto-settle", "Needs approval", "Blocked". The data field `route_label` adds a sort prefix (`1 Auto-settle`, `2 Needs approval`, `3 Blocked`) so Studio axes sort in route order. The boilerplate does the same with its numbered aging buckets.

### 4.4 Type, spacing, motion

- **Fonts:** Inter for the UI and JetBrains Mono for hashes, IDs and code, both from Google Fonts. Studio can load Google fonts itself through `loadThemeGoogleFonts`. Pass the same font family to its theme.
- **Scale:** 12 / 13 / 14 (body) / 16 / 20 / 24 / 32 px. KPI values use 24–32 px with `tabular-nums`.
- **Spacing:** a 4 px base, 16 px gaps inside cards, 24 px between sections. The Studio canvas uses its own `studioWidgetPadding`.
- **Motion tokens:** `--pg-ease: cubic-bezier(.2,.8,.2,1)`, `--pg-fast: 150ms`, `--pg-base: 220ms`, `--pg-slow: 300ms`. Wrap every animation in `@media (prefers-reduced-motion: no-preference)`.

### 4.5 Wiring: one set of tokens, four consumers

```text
index.css :root / [data-theme=dark]  ──  --pg-* CSS variables (single source)
   ├── Tailwind v4   @theme inline { --color-surface: var(--pg-surface); --color-auto: var(--pg-auto); … }
   │                 → classes like bg-surface, text-ink-2, border-border, bg-auto-soft, text-blocked
   ├── AG Studio     studioTheme.withParams({ backgroundColor: 'var(--pg-surface)', foregroundColor: 'var(--pg-ink)', … })
   │                 + --ag-chart-palette-fills-N-color: var(--pg-chart-N)
   ├── AG Grid       studioGridTheme inside custom widgets; themeQuartz.withParams({ accentColor: 'var(--pg-primary)' }) if used standalone
   └── Custom widgets  read var(--pg-*) directly in SVG fill/stroke (non-AG-Charts widgets don't get the report theme)
```

**Dark mode switch** (`src/app/theme.ts`): a single `setTheme(mode)` sets both `document.documentElement.dataset.theme = mode` (our tokens) and `document.body.dataset.agThemeMode = mode` (Studio's documented switch). The choice is saved in `localStorage` (wrapped in try/catch) and defaults to `prefers-color-scheme`.

**Studio theme sketch** (`src/studio/theme.ts`). The pattern follows the boilerplate's `studio/theme.ts`. Param names other than `backgroundColor`, `foregroundColor`, `browserColorScheme`, `accentColor` and `fontFamily` are **(verify)** against the Studio Theme reference.

```ts
import { studioTheme } from 'ag-studio'
const v = (name: string) => `var(--pg-${name})`
export const pactguardTheme = studioTheme
  .withParams({ backgroundColor: v('surface'), foregroundColor: v('ink'), accentColor: v('primary'),
                fontFamily: 'Inter, ui-sans-serif, system-ui', browserColorScheme: 'light' }, 'light')
  .withParams({ backgroundColor: v('surface'), foregroundColor: v('ink'), accentColor: v('primary'),
                fontFamily: 'Inter, ui-sans-serif, system-ui', browserColorScheme: 'dark' }, 'dark')
```

**CSS layering:** Tailwind v4 uses cascade layers. In the UI-0.4 spike Studio rendered correctly next to Tailwind's preflight with no extra setting, so `themeCssLayer` stays unset. If a conflict appears, `themeCssLayer` takes any layer name we choose (Studio wraps its CSS in `@layer <name>`). The type docs recommend also setting `themeStyleContainer: document.body`.

### 4.6 Primitives (`frontend/src/ui/`)

| Primitive | Replaces | Notes |
|---|---|---|
| `Card` (`title`, `meta`, `actions`) | The repeated `rounded-lg border bg-white p-4` | Section header slot with a numbered stage chip |
| `Badge` (`tone`: auto, human, blocked, evidence, live, sim, neutral) | The `status`, `badge` and `route` maps in four files | The only place route colours are chosen |
| `Stat` | The local `Stat` in `DealCard` and the tiles in `SummaryStrip` | Label, value, sub-line and an optional delta chip |
| `Money` | `money()` calls in JSX | `tabular-nums`, with a negative/positive tone option |
| `Hash` | `short()` calls in JSX | Mono font, evidence colour, copy on click, full value in a tooltip |
| `Button` (`variant`: primary, secondary, danger, ghost) | Ad-hoc button classes | Visible focus ring, a `busy` state, an optional shortcut hint |
| `Drawer` | — | Right-side sheet for the Firewall Checkpoint and the lineage view. Traps focus and closes on Esc. |
| `Tabs`, `EmptyState`, `Skeleton`, `ErrorBanner` | Ad-hoc `<p>` errors | Every screen uses these in the polish sweep |

Icons come from `lucide-react`. It's tree-shaken, MIT-licensed, and the only icon dependency.

---

## 5. Screens

### 5.1 App shell

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ ◆ PactGuard   Mission Control   Command Center   Disputes        ● REPLAY  ⛓ chain ok · 42  ☾  ⌘K │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ ① Delegate ━ ② Discover ━ ③ Govern ━ ④ Settle ━ ⑤ Verify ━ ⑥ Reconcile ━ ⑦ Pay out ━ ⑧ Defend ━ ⑨ Observe ━ ⑩ Learn │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Navigation:** hash routes (`#/run`, `#/studio`, `#/disputes`) through a small `useHashRoute` hook. We don't need a router dependency for three screens.
- **Status area:** the mode badge (REPLAY / LIVE SANDBOX, from `/api/health`), the chain badge (from `/api/ledger/verify`, polled after each run event), the theme toggle and the ⌘K command palette.
- **Stage Rail:** ten numbered stages from doc 09. Each one is idle, active (pulsing), done or refused, driven by SSE `stage` values. Clicking a stage scrolls to its section.
- **⌘K palette** (Should): "Run agent", "Simulate attack", "Toggle theme", "Ask Copilot…". The last one opens the Command Center with the prompt pre-filled.

### 5.2 Mission Control (the live run, built in our own React)

```text
┌─────────── 4 cols, sticky ──────────┬──────────────────────────── 8 cols ────────────────────────────┐
│ MANDATE                       [Edit] │ ② MARKET · Channel3 live                                       │
│ ops@acme · Equip a 5-person office   │   27" 4K monitor ×5   baseline $229   [card][card][card]       │
│ Budget  $1,138 / $2,200  ▓▓▓▓▓░░░░   │                                                                 │
│ ── Mandate Ruler ─────────────────── │ ② NEGOTIATION · 3 bounded turns · simulated sellers            │
│ $0      auto│$300           cap│$1.5k│   Northwind ●───●───● $204  ✓ COMMITTED                         │
│  ● webcams        ● monitors   ✕ $900│   Contoso   ●───●───● $212    cancelled                         │
│ mode: auto ▾  allowlist 2  cats 3    │   Fabrikam  ●───✗ schema gate                                   │
│ [ Run agent ▶ ]                      │   ┄┄┄┄┄┄┄┄ retail baseline $229 ┄┄┄┄┄┄┄┄                          │
│                                      │                                                                 │
│ RED TEAM                             │ ③④ DEALS                                                        │
│ [ ⚠ Simulate prompt injection ]      │   4K monitors ×5    $1,020   ▲ Needs approval  [Review →]       │
│                                      │   Webcams ×5        $118     ✓ Auto-settled    [Receipt]        │
├──────────────────────────────────────┴─────────────────────────────────────────────────────────────────┤
│ ticker ▸ 14 ④ captured …a91f · 13 ③ AUTO_SETTLE 0.31 ms · 12 ② committed Northwind …   [filter ▾]       │
└───────────────────────────────────────────────────────────────────────────────────────────────────────┘
          Drawer → FIREWALL CHECKPOINT: [Warrant ✓][Reversibility ✗ terms hidden][Price norm ✓][Budget ✓]
                   → route + ⏱ 0.42 ms → [Approve ⏎] [Reject] → PayPal button → Decide-and-Prove receipt
```

Below 1024 px wide, the columns stack and the Mandate card collapses into a summary bar.

### 5.3 Command Center (AG Studio, full width)

```text
┌ Overview | Firewall | Savings | Audit | Defend ─────────── [Present ⇄ Edit] [↺ Curated] [✦ Copilot] ┐
│ [date: last 30 days]  [route: Auto · Approval · Blocked]   data: seeded history + this run ⓘ         │
│ ┌ Spend ┐┌ Saved ┐┌ Auto-rate ┐┌ Blocked ┐┌ Chain ┐                                                │
│ │$18.2k ││ $2.9k ││   64 %    ││    7    ││ 412 ✓ │                                                │
│ ┌──── W1 Mandate Ruler ─────────────────────┐┌──── Routes over time (line) ─────┐                   │
│ ┌──── Transactions (grid) ──────────────────┐┌──── W3 Lineage Chain ────────────┐ ← cross-filtered  │
└─────────────────────────────────────────────────────────────────────────────────── Copilot panel ──┘
```

| Page | Widgets (built-in unless marked W) | Story |
|---|---|---|
| **Overview** | `value` ×5 (spend, saved, auto-rate, blocked attempts, ledger entries), **W1 Mandate Ruler**, `line-chart` routes over time, `grid` transactions, **W3 Lineage Chain** | "Where every dollar sits relative to the mandate" |
| **Firewall** | **W4 Firewall Flow** (Should), `bar-chart-stacked` failed factor × route, `scatter-chart` amount × firewall_ms, `grid` blocked reasons, `button-filter` route | "Why the agent was stopped, and how fast" |
| **Savings** | **W2 Savings Dumbbell**, `bar-chart-grouped` savings by vendor, `value` savings rate (calculated), `line-chart` negotiation convergence (turn × unit price by seller) | "Negotiation beats the retail baseline" |
| **Audit** | `grid` transactions, **W3 Lineage Chain**, `pivot-grid` vendor × route, `value` chain status | "Every action is sealed and traceable" |
| **Defend** (Phase 3) | `radial-gauge` dispute win odds, `grid` disputes, `bar-chart-stacked` payout gross vs net, nudge scoreboard (Could) | "We defend from the seal and pay out only when verified" |
| **Incidents** (built live by the agent) | Whatever the Sentinel builds | "Agents use the dashboard too" |

> **As built (2026-11-12).** The pages shipped differ from this sketch. **Agent group:** `Purchases` (spend, savings by vendor and category, firewall routes by week, dispute outcomes beside supplier trust, the transactions grid) and `Agent Activity` (firewall decisions, latency, human escalations, an escalations queue). **PayPal account group:** `Revenue`, `Receivables`, `Cash`, `Catalogue`. The custom widgets W1 to W5 and the Sentinel's Incidents page were not built. Studio draws no page tabs, so the host draws them.

**Present vs Edit:** Present maps to Studio `mode="view"` with the panels hidden. It's the default, and the one we record. Edit maps to `mode="edit"`. "↺ Curated" restores the curated `initialState` through `api.setState` (remember to re-sync anything that listens for state changes; see §6.10).

### 5.4 Disputes desk (Phase 3)

The left side shows the triage queue from `GET /api/disputes`, sorted by deadline. The right side shows the **DisputeCard**:

- reason and amount
- deadline countdown
- win-odds gauge
- sealed terms hash (`Hash`)
- delivery verdict
- "chain verified" badge
- missing records, as a checklist
- evidence PDF preview (`<iframe>` of the PDF)
- **Submit evidence**: a primary button with a confirmation step (D-4: draft, then one-click submit)

Below it, the **Payout gate** shows two locks, `VERIFIED` and `RECONCILED`. Each lock opens when its token is minted, and the payout releases when both are open. A gross-to-net bar carries the label "fee rate illustrative".

### 5.5 Signature interactions

These are ranked by demo value against build cost. "Must" items are on the critical path. The rest follow the cut order in §14.

| # | Interaction | Why it lands | Cost | Priority |
|---|---|---|---|---|
| 1 | **Mandate Ruler.** The auto-purchase line from `arXiv:2610.29216`, drawn as a dollar axis with three zones. Every deal is a dot and the attack is a ✕ beyond the cap. The same component appears in Mission Control and as Studio widget W1. | It explains the firewall in one picture, and links the run screen to the dashboard | M | Must |
| 2 | **Firewall Checkpoint.** The four factors light up in sequence (≈60 ms apart, for show only; the real decision takes under 1 ms and the stopwatch says so), then the route stamp, then Approve. | The governance moment the PayPal judges care about | M | Must |
| 3 | **Stage Rail** driven by SSE | Shows where the run is at a glance | S | Must |
| 4 | **Decide-and-Prove receipt.** A receipt-style card with a perforated edge, order and capture IDs, terms hash, decision digest, and "copy lineage". | Makes "proof" something you can see | S | Must |
| 5 | **Copilot builds a widget live.** Our agent delegates to Studio's built-in Page and Widget agents. | Directly meets the AG prize criterion | M | Must |
| 6 | **Lineage Chain.** Hash-linked blocks for one lineage, with prev → entry links and a "chain verified" seal. | Pain point #5 made visible | M | Must |
| 7 | **Attack Theatre.** The page edge turns red, the injected payload is shown with the malicious span highlighted, then a BLOCKED stamp. In the Command Center, the Sentinel adds an incident widget. | Drama, and agents acting on the dashboard | M | Should |
| 8 | **Negotiation race lanes.** Each seller's price moves toward and below the dashed baseline over three turns. The schema-gate stamp appears on the dropped seller and a commitment seal on the winner. | Turns a table into a story | M | Should |
| 9 | **Mandate v1 → v2 diff.** Shown as a code-style diff (removed vendor in red, new threshold in green) with the trust deltas that caused it. | The "rules improve" ending | S | Must (doc 10, Phase 2) |
| 10 | **Present mode.** Hotkeys step through the beats, type is larger, and dev controls are hidden. | Clean takes for the video | S | Must (Phase 5) |

---

## 6. AG Studio reference (version 3.0.0, read 2026-11-01)

Sources are listed in §15. **(verify)** means we haven't confirmed it, so check it against the installed package before relying on it.

### 6.1 Packages and compatibility
- Install `ag-studio@3.0.0` and `ag-studio-react@3.0.0`. The boilerplate pins exactly these versions, with `ag-grid-community` and `ag-grid-react` 36.2.0.
- Studio 3.0 goes with **AG Grid 36.2** and **AG Charts 14.2**. Any standalone AG Grid on the same page should match.
- Supported: React 17–19+, TypeScript ≥ 5.8.3, and the two latest major versions of Chrome, Firefox, Edge and Safari.
- The licence covers Studio and its built-in grid and chart widgets. AG Grid or AG Charts **Enterprise** inside a custom widget needs its own licence. We avoid that by building custom widgets in plain SVG.
- **Our licence (B-6, closed 2026-11-01):** an AG Studio Pro with AI trial, valid until 2026-12-16, which covers the Nov 12 deadline and judging. It's an evaluation licence for a single application.
  - It lives in `frontend/.env.local` (gitignored by `*.local`) as `VITE_AG_STUDIO_LICENSE`. `frontend/.env.example` documents the name.
  - On Render, set the same variable on the static site. Vite reads it at build time.
  - It goes on `<AgStudioProvider licenseKey modules={[AgStudioAiModule]}>`. When it validates, the `ag-studio-watermark` and `ag-watermark` elements carry `ag-hidden` and the console shows no licence warning.
- Without a licence Studio still runs for local testing, with a watermark and console warnings.

### 6.2 Mounting
```tsx
import { AgStudio, AgStudioProvider } from 'ag-studio-react'
import { AgStudioAiModule, enableStudioDevValidations } from 'ag-studio'
if (import.meta.env.DEV) enableStudioDevValidations()          // docs use process.env.NODE_ENV (Next.js)
<AgStudioProvider licenseKey={import.meta.env.VITE_AG_STUDIO_LICENSE} modules={aiOn ? [AgStudioAiModule] : undefined}>
  <AgStudio style={{ height: '100%', width: '100%' }} theme={pactguardTheme} data={studioData}
            initialState={curatedReport} mode={mode} widgets={widgets} ai={ai} layout={{ widgetBorderEnabled: true }}
            onApiReady={(e) => (apiRef.current = e.api)} onStateUpdated={(e) => save(e.state)} />
</AgStudioProvider>
```
- Studio fills a parent with a set size. Under Tailwind preflight, make sure the height chain is set: `html, body, #root` at 100%, and the Studio container `h-[calc(100dvh-var(--shell-h))]`.
- Lazy-load the Command Center (`React.lazy`) so Mission Control doesn't pay for Studio's bundle. **Measured in UI-0.4:** the Studio chunk is 5.4 MB minified (1.5 MB gzipped), while the main chunk stays at 245 KB.
- The licence key reaches the browser in every setup, the boilerplate's included. A `VITE_` variable is acceptable for this key. **Never** put an LLM key in a `VITE_` variable.
- `initialState`, `ai` and `context` are read once at initialisation. `mode`, `theme`, `layout`, `panels` and `widgets` can change later.

### 6.3 Data model
- `data: AgDataSourcesDefinition = { sources, relationships?, expressions?, calendars?, buckets?, description?, formats?, options? }`.
- A source is `{ id, name?, description, data: Row[], fields }`. Each field has an id, a name and a format: `textFormat`, `dateFormat`, `dateTimeFormat`, `currencyFormat`, `integerFormat`, `decimalFormat`, `booleanFormat` or `percentageFormat`. State references fields as `"<sourceId>.<field>"`.
- Relationships: `{ type: 'many-to-one', source: { tableId, fieldId }, target: { tableId, fieldId } }`. The boilerplate wraps this in a `manyToOne(id, 'a.x', 'b.y')` helper.
- Calendars: date fields bind to a shared calendar with buckets `year`, `quarter`, `month`, `week`, `day` and `dayOfWeek`.
- Calculated measures: `{ expression: { operator: 'divide', inputs: [sumOf(a), sumOf(b)] }, isMeasure: true }`.
- Source and field `description`s are what the agents read. Write them as if for a new analyst.
- Refreshing after a run: call `api.setData(...)` with the same schema **(verify)**. Changing the schema needs a remount (`api.destroy()` and mount again).

### 6.4 Report state, layout, modes, panels
- `AgReportState = { pages: [{ id, widgets: { [id]: { type, dataMapping, format? } }, widgetLayout: { [id]: { xTrack, yTrack, xSpan, ySpan } }, filter?, layout? }], selectedPageId, panels? }`. The canvas has 24 tracks (`studioCanvasColumnsScale: 24` in the theme defaults), and `xTrack` starts at 0. Widget state references fields as `"<sourceId>.<fieldId>"`, for example `transactions.amount` (confirmed in UI-0.4).
- Studio keeps no page titles. Store `pageTitles` alongside the state, as the boilerplate does.
- To build the curated report: lay it out in edit mode, call `api.getState()`, and commit the JSON to `src/studio/report.ts`. Then tidy the spans by hand.
- Runtime control: `api.getState()`, `api.setState(next)` (immutable; compared by reference), `api.setProperty('mode', 'view')`, plus `undo`, `redo` and `clearHistory`.
- `mode`: `'edit' | 'view'`, default `'view'`. View mode hides every editing control. `enableFilterEditingInViewMode` lets viewers change filters.
- `panels: { edit: { left: ['filters'], right: ['edit', 'data'] }, view: { left: [] } }`. The panel IDs are `ai`, `filters`, `edit` and `data`. To start a panel collapsed, use `initialState.panels.<id>.collapsed`.
- `layout`: `columns`, `rowHeight`, `minWidth` (default 720 px), `maxWidth`, `height` and `pagePadding`. Below `minWidth` the page scrolls sideways. There are no breakpoints.
- Known issue (boilerplate comment): a **relative** date filter in saved state doesn't apply on load. Use absolute ranges in the curated state.

### 6.5 Custom widgets
- Register through `widgets={(cfg) => createWidgets<Registry>({ additionalTypes: [defs], menu: [...cfg.menu, { label: 'PactGuard', widgetIds: [...] }] })}`. Import `createWidgets` from **`ag-studio-react`**, not `ag-studio`.
- Definition fields:
  - `id`, `label`, `icon`
  - `dataMapping` (slots)
  - `form` (built with `params.createDefaults({ dataMappingItems, supportsCrossHighlight })`, extended with nodes such as `{ type: 'number', id: 'format.style.x', label, defaultValue }`)
  - `formatShape` and `ai: { description }`. **Both are required** before agents can use the widget.
  - `defaultState`, `comp` (a React component taking `AgWidgetParams`), `defaultSize`, `minSize`, `toolbar`, `featureConfig`
- A slot looks like `{ type: 'field' | 'fieldset', supportedRoles: ['category' | 'numeric' | 'temporal'], requires?: { cardinality, per }, required, sort, aiDescription }`.
- Data loop: `widgetApi.setDisplayState('loading')`, then `await widgetApi.getData({ fields, sort?, filter?, limit? })`, then render `results`, then `setDisplayState('displayed')`. Page filters and cross-filters are applied automatically. Parallel requests need distinct `queryId`s, or the later request cancels the earlier one. Drop stale responses in the effect cleanup.
- Display states: `displayed`, `loading` (`{ prominent: false }` for a soft refresh), `noData`, `incompleteDataMapping`. **Use all four.**
- `widgetApi.getSchema()` lists tables and fields, so a widget can work without a mapping.
- Popups rendered outside the widget's DOM need the class `ag-custom-component-popup`.
- The helpers `category()`, `numeric()` and `formWithoutCrossFilter()` appear only in the "88 seconds" blog post **(verify)**. Prefer the explicit objects shown in the docs.

### 6.6 Cross-filtering
- Opt in with `featureConfig: { crossFilter: { supportsHighlight: true } }`. The response then carries `crossFilter` data so the widget can dim unselected marks.
- Call `toggleCrossFilter(...)`, `resetCrossFilter()` and `getCrossFilterSelections()`. Probably on `widgetApi` **(verify)**.
- Multi-value: `{ type: 'multiValue', values: [{ field, value }, …], group: 0 }`. The single-value payload shape is **(verify)**.
- Built-in filter widgets: `button-filter`, `list-filter` and `date-filter`. Column and bar charts highlight on click when `format.crossFilter: 'highlight'` is set.

### 6.7 Theming
- `studioTheme.withParams(params, modeName)` can be chained, one call per mode. Switch modes with `data-ag-theme-mode` on `<html>` or `<body>`.
- Params come in four prefixes: shared (no prefix), `studio*`, `grid*` and `chart*`. Each one is also a CSS variable, `--ag-<kebab-name>`, for example `--ag-chart-palette-fills-1-color`.
- Inside custom widgets: AG Grid takes `theme: studioGridTheme`. AG Charts takes `theme: getChartTheme(api)` with a transparent background. Anything else (our SVG) styles itself from `var(--pg-*)`.
- Keep custom CSS selectors to single class names, because the DOM changes between releases.
- The Figma design system's variable names match the theming params. Optional: design the theme in Figma and export it with the script in `ag-grid/ag-grid-figma-design-system`.

### 6.8 Agent framework
- **Opt-in, bring your own LLM.** Studio ships no model and no adapter. The harness runs **in the browser**.
- **Five built-in agents:** Lead (primary), Planning, Data, Page and Widget.
  - Their model-facing tools include `view_schema`, `view_report`, `view_page`, `view_plan`, `create_plan`, `execute_query`, `create_expression`, `add_widget`, `position_widget`, `remove_widget`, `add_page_filter`, `configure_widget`, `add_widget_filter` and `delegate_to`.
  - They have the same powers as a user, writes included.
  - The built-in Lead delegates only to the fixed built-in set, so it won't find our agents. That's why we bring our own primary.
- **Harness:**
  ```ts
  createAiHarness(api, ({ builtIn, tools }) => ({
    agents: [...Object.values(builtIn).map((d) => directLlmRunner({ ...d, adapter })), ...ours],
    primary: 'copilot', promptStarters, models }))
  ```
  The shorthand `createAiHarness(api, { adapter, promptStarters, models })` runs the five built-ins only.
- **Agent definition:** `{ id, name, description, schema, instructions: () => string, tools: () => tool[], maxTurns }`.
  - Use callbacks for `instructions` and `tools`, and never snapshot them, so they stay current.
  - A primary agent needs `schema: (s) => s.undefined()`.
- **Delegation:** `tools.delegateTo(['planning', 'page', 'widget', 'data', 'auditor'])`. The targets need a `description`. The child run reports back through `complete_task`, and the chat panel shows it inline.
- **Tools:**
  - `const studio = api.getAiTools()` gives the factories `studio.viewSchema()`, `studio.viewPage()`, `studio.viewWidget()`, `studio.executeQuery()`, `studio.addWidget()`, `studio.positionWidget()` and `studio.configureWidget({ widgetType, widgetId })`.
  - Custom tools: `api.defineAiTool({ name, description, params: (s) => s.object({ … }), execute: async (args, ctx) => ctx.success(response, data) | ctx.error(msg) })`.
  - `ctx.signal` is for aborting `fetch`. A tool can call our backend.
- **Runners:**
  - `directLlmRunner`: Studio runs the loop and the adapter only calls the model. **We use this one.**
  - `clientToolRunner({ run: async function* (input, ctx) })`: our own server produces the turns as AG-UI events, and Studio still executes the tools. A stretch goal if we want the loop on FastAPI.
  - A fully custom runner is also possible.
- **Adapter contract (`AgLlmAdapter`):** `executeTurn(request, { signal })` returns `{ stream, complete }`.
  - `request`: `{ input, instructions, tools: [{ name, description, parameters }], toolChoice, responseFormat, model?: { id, effort } }`
  - `stream` events: `TEXT_MESSAGE_START/CONTENT/END`, `TOOL_CALL_START/ARGS/END` (or the `*_CHUNK` shorthands), `REASONING_MESSAGE_*`
  - `complete` returns `{ status, output, usage, error }`
  - The adapter doesn't execute tools. Results return on the next turn as `function_call_output` items, which follow the OpenAI Responses shape. The boilerplate's `openai-adapter.ts` is the exact reference for the item shapes.
- **Programmatic prompts:** keep a reference to the harness, then call `const s = await harness.createThread({ agentId: 'sentinel' }); s.sendMessage('…')`. To use our own chat UI, subscribe with `s.addEventListener('changed', …)` and read `s.messages` and `s.status`.
- **Chat panel:** it appears once `ai` is set. Open or close it through the `ai` panel ID. Configure `promptStarters: [{ label, prompt, icon? }]` and `models: [{ id, label, efforts? }]`. Prompt starters show only before the first message.
- **Guardrails:** there is no Studio-wide read-only mode for agents. Control comes from which tools each agent gets, plus `delegateTo` targets and `maxTurns` (default 100). Studio's own harness doesn't pause for tool approval yet.

### 6.9 WebMCP (stretch)
- `api.getAiTools()` exposes 15 live tools. The example bridge `webmcpBridge.ts` publishes four of them read-only (`view_schema`, `view_page`, `view_widget`, `execute_query`) through `document.modelContext.registerTool`.
- It needs Chrome 149+, a secure context, and the origin trial or `chrome://flags/#enable-webmcp-testing`. Re-sync the published tools after every `api.setState` call, because `setState` doesn't fire `stateUpdated`. Labelled experimental.

### 6.10 Gotchas we already know about
- `process.env.NODE_ENV` becomes `import.meta.env.DEV`. Drop `"use client"`.
- `api.setState()` doesn't fire `stateUpdated`, so update anything that depends on it yourself.
- Swapping `data` doesn't rebuild the field schema.
- A relative date filter in saved state fails on load.
- The `execute_query` params sit under a `query` key.
- Non-AG-Charts custom widgets don't get the report theme, so style them yourself.
- An agent that replies but never acts usually means the adapter isn't relaying tool calls.
- If `primary` doesn't name a registered agent, the panel shows "AI is unavailable".
- Studio's default theme makes AG Charts log `theme.params.chartPadding cannot be set to -1` once per load. It's harmless and doesn't come from our theme.

### 6.11 Still to verify (check in UI-0.4 and UI-2.6 and record the answer here)
- [x] The 24-track grid width. **Yes:** `studioCanvasColumnsScale: 24`, and `xTrack` starts at 0.
- [ ] Which object `toggleCrossFilter` lives on, and the single-value payload shape
- [ ] `api.setData` refresh behaviour. Partly answered by the `data` prop's type docs: a new `data` value updates synchronous rows, while adding or removing sources or changing fields is ignored. Not tested yet.
- [x] React prop names: `onStudioReady`, `onRenderStateChanged` and `onErrorRaised`, plus `onApiReady`, `onStateUpdated` and `onStudioPreDestroyed`.
- [x] `themeCssLayer` alongside Tailwind v4: not needed so far (see §4.5).
- [ ] Per-series colour control in built-in chart `format`, for route colours
- [ ] Exact `AgAiConversationItem` and `function_call` shapes (copy from the boilerplate's `openai-adapter.ts`)
- [ ] The `delegateTo` source (the harness builder's `tools` argument versus `api.getAiTools()`)
- [ ] Whether Studio's PDF export is in 3.0.0

---

## 7. Decisions

| ID | Decision | Why |
|---|---|---|
| D-UI-1 | **Mission Control stays custom React. AG Studio is the analytics screen.** They share tokens, primitives and the Mandate Ruler. | The run is a guided, interactive sequence (approve, PayPal popup, attack) with SSE. Studio is built for self-serve analysis. Forcing the run into widgets would cost days and make the governance story harder to follow. |
| D-UI-2 | **Claude through our own `AgLlmAdapter`, proxied by FastAPI (`POST /api/ai/turn`).** The key stays on the server. | Studio has no Claude adapter. The adapter's request and response shape is documented, and the proxy is a format translator. |
| D-UI-3 | **No Studio agent can move money.** No agent tool calls approve, prepare, capture, pay out or change a mandate. The proxy enforces a tool allowlist. | Doc 10 §2.3 rule 1. AG's own advice is not to give the model tools it shouldn't have. |
| D-UI-4 | **No component library.** Tailwind plus our own `src/ui` primitives. The only new dependencies are `ag-studio`, `ag-studio-react`, `lucide-react`, `@paypal/react-paypal-js` (Phase 1b) and optionally `d3-sankey` (W4). | Keeps the bundle and the learning curve small. One look throughout. |
| D-UI-5 | **Custom widgets are SVG + React, not AG Charts Enterprise.** | No extra licence. Full control of the route colours. |
| D-UI-6 | **Present mode is the default** for Studio (`mode="view"`) and for the recording | Judges see the finished report. The Edit toggle shows the self-serve side. |

---

## 8. Command Center data contract (backend, Phase 2a)

**New endpoint `GET /api/studio/sources?run_id=`.** It returns `{ asOf, sources: { transactions, factors, offers, ledger, suppliers } }`, built from the ledger by `s09_observe`. Each row in it comes from the real code path, as doc 10 §2a requires. The existing `/api/studio/rows` stays for compatibility.

| Source | One row per | Columns (✱ = new) | Key relationships |
|---|---|---|---|
| `transactions` | lineage | Existing stable keys (doc 10 §2a) + ✱`created_at` (first decision entry), ✱`run_id`, ✱`origin` (`seeded`, `replay` or `live`), ✱`route_label`, ✱`unit_price`, ✱`quantity`, ✱`baseline_amount`, ✱`method`, ✱`primary_reason` (first failed factor, or "All checks passed"), ✱`is_auto`, ✱`is_human`, ✱`is_blocked` (0/1) | `vendor` → `suppliers.vendor` (many-to-one) |
| `factors` | lineage × factor | `lineage_id`, `factor`, `passed` (bool), `hard` (bool), `detail` | → `transactions.lineage_id` (many-to-one) |
| `offers` | seller × turn × negotiation | `negotiation_id`, `category`, `seller_id`, `turn`, `unit_price`, `baseline`, `dropped` (bool), `reservation` | — (the convergence chart filters by category) |
| `ledger` | ledger entry | `seq`, `lineage_id`, `stage`, `kind`, `entry_hash`, `prev_hash`, `created_at` | → `transactions.lineage_id` (many-to-one) |
| `suppliers` | vendor | `vendor`, `trust_before`, `trust_after`, `wins`, `disputes_lost`, `on_allowlist_v2` (bool) | — |
| `disputes`, `payouts` (Phase 3) | dispute / payout | Taken from the `s08` triage and the `s07` release | → `transactions.lineage_id` |

**Studio definition (`src/studio/data.ts`):**
- **Formats:** `currencyFormat` for amounts, `percentageFormat` for odds and rates, `dateTimeFormat` for `created_at`, `decimalFormat` for `firewall_ms`.
- **Calendar:** one calendar on `transactions.created_at` and `ledger.created_at`.
- **Expressions:**
  - `savings_rate = sum(savings) / sum(baseline_amount)`
  - `auto_rate = sum(is_auto) / count(lineage_id)`
  - `block_rate = sum(is_blocked) / count(lineage_id)`
- **Descriptions:** every source and field gets one, written for the agent. Include the glossary: lineage format `PG-…`, the meaning of each route and the four factors.

**Tests:**
- `test_studio_sources_columns_are_stable`. Widgets and the curated report bind to these keys.
- `test_studio_sources_rows_come_from_ledger`. Seeded rows have decision entries.

---

## 9. Custom widget specs

Every widget meets these requirements:
- all four display states
- `formatShape` + `ai.description` + `aiDescription` on every slot
- cross-filter highlight, except where noted
- colours only from `var(--pg-*)`
- keyboard focus on marks (Enter toggles the cross-filter)
- an accessible `<title>` and `<desc>` in the SVG

The files live in `frontend/src/studio/widgets/<Name>.tsx`. They register in `widgets/index.ts` under the "PactGuard" menu group.

### W1 `pg-mandate-ruler`: Mandate Ruler (Must)
- **Shows:** a dollar axis from $0 to max(cap × 1.25, largest amount), with three tinted zones. Auto runs up to `autoThreshold`, approval from there up to `perTxnCap`, blocked beyond it. Each transaction is a dot, jittered vertically by route. Blocked attempts are ✕. Hovering shows vendor, amount, route and primary reason.
- **Slots:**
  - `amount`: field, numeric, required. aiDescription: "Transaction amount in USD".
  - `route`: field, category, required. "Firewall route label".
  - `id`: field, category, required. "Lineage ID, used for cross-filter".
  - `label`: field, category, optional. "Vendor or item name".
- **Form options:** `autoThreshold` (default 300), `perTxnCap` (default 1500), `showBudget` (bool). The defaults follow D-3.
- **Cross-filter:** clicking a dot toggles `lineage_id`. Other selections dim.
- **Shared code:** the drawing lives in `src/ui/MandateRuler.tsx`. Mission Control (UI-1.3) uses it with data from the run snapshot.
- **Fallback:** a built-in `scatter-chart` (amount × firewall_ms).

### W2 `pg-savings-dumbbell`: Savings vs baseline (Must)
- **Shows:** one row per vendor or category. A hollow dot marks the retail baseline and a filled dot marks the negotiated amount, joined by a bar. The savings % sits on the right, and rows are sorted by savings.
- **Slots:**
  - `group`: field, category, required
  - `baseline`: field, numeric, sum, required
  - `actual`: field, numeric, sum, required
- **Cross-filter:** clicking a row toggles `group`.
- **Fallback:** `bar-chart-grouped` with baseline vs amount.

### W3 `pg-lineage-chain`: Lineage Chain (Must)
- **Shows:** the ledger entries for the lineage selected through cross-filter, as a vertical chain of blocks. Each block has a stage chip, the kind, `Hash(entry_hash)`, and the time. The connector between blocks is labelled with `prev_hash`, and each block shows its own `entry_hash`. A header seal shows "chain verified · N entries" from `/api/ledger/verify`.
- **Slots:** reads the `ledger` source through `getSchema()` and `getData`. No mapping is needed, so the widget works when dropped on a page.
- **States:**
  - `noData` with the text "Select a transaction to trace its lineage" when no single lineage is selected.
  - `loading` with `{ prominent: false }` on refresh.
- **Cross-filter:** receive only. It doesn't emit selections.
- **Fallback:** a `grid` over `ledger`.

### W4 `pg-firewall-flow`: Firewall Flow (Should)
- **Shows:** a Sankey from category to `primary_reason` to `route_label`, with link width equal to the count. Built with `d3-sankey`. The pattern follows the docs' Sankey example.
- **Slots:**
  - `from`, `via` and `to`: each a field, category
  - `value`: field, numeric, count
- **Cross-filter:** clicking a link sends `multiValue` with the pair `[{field: from, value}, {field: via, value}]`.
- **Fallback:** `bar-chart-stacked` with `primary_reason` × `route_label`.

### W5 `pg-trust-board`: Supplier trust scoreboard (Could)
- **Shows:** supplier rows with a trust gauge going from before to after, an arrow for the change, win and dispute counts, and an "allowlist v2: removed" chip. It's styled as a scoreboard, not a report, following AG's nudge-bot idea. It sets up the mandate v2 diff.
- **Slots:**
  - `supplier`: category
  - `before` and `after`: numeric
- **Fallback:** a `grid` with conditional formatting.

---

## 10. Agent layer

### 10.1 Pieces

```text
Browser (Studio harness)                                   FastAPI
┌──────────────────────────────────────────────────┐       ┌────────────────────────────────────────┐
│ copilot (primary, ours)                          │       │ POST /api/ai/turn  (SSE)               │
│   tools: view_schema, view_page, execute_query,  │       │  1 check model ∈ allowlist             │
│          delegate_to[planning,page,widget,data,  │ ────▶ │  2 check every tool name ∈ allowlist   │
│                      auditor]                    │       │  3 translate request → Claude Messages │
│ auditor (ours, read-only)                        │       │  4 stream Claude events → AG-UI events │
│   tools: view_schema, execute_query,             │ ◀──── │  5 no tools execute server-side        │
│          trace_lineage*, verify_chain*           │       │  ANTHROPIC_API_KEY stays here          │
│ sentinel (ours) → delegate_to[page, widget]      │       └────────────────────────────────────────┘
│ built-ins: lead, planning, data, page, widget    │       * custom tools call GET /api/ledger?lineage=…
│ adapter: claudeAdapter → fetch('/api/ai/turn')   │         and GET /api/ledger/verify (read-only)
└──────────────────────────────────────────────────┘
```

### 10.2 Agents

| Agent | Role | Tools | Notes |
|---|---|---|---|
| `copilot` "PactGuard Copilot" (**primary**) | Answers questions and builds dashboards by delegating | `view_schema`, `view_page`, `execute_query`, `delegate_to` | This is the "custom agent talking to Studio's built-in agents". Its instructions carry the domain glossary and the current page, from `api.getState().selectedPageId`. |
| `auditor` "Evidence Auditor" | Explains why a transaction was routed the way it was, and proves it from the ledger | `view_schema`, `execute_query`, `trace_lineage`, `verify_chain` | Read-only. `schema: s.object({ lineage_id: s.string().optional() })` |
| `sentinel` "Anomaly Sentinel" | Builds or updates an **Incidents** page when an attack is blocked | `view_schema`, `execute_query`, `delegate_to` (page, widget) | Triggered by code, not by a user. Mission Control's attack result calls `harness.createThread({ agentId: 'sentinel' })` and then `sendMessage(...)` with the blocked payload summary. With no key, it falls back to a pre-written incident page set through `api.setState`. |
| Built-ins: `lead`, `planning`, `data`, `page`, `widget` | Studio's own team | Studio's | Registered through `directLlmRunner({ ...d, adapter })`. Reached as delegation targets. |

**Prompt starters:**
- "Savings by supplier vs retail baseline, highlight blocked attempts"
- "Which firewall factor blocks the most spend?"
- "Trace the lineage of the largest approved order"
- "Build an incident page for blocked prompt-injection attempts"

**Models:**

| Model | Label | Role |
|---|---|---|
| `claude-sonnet-5-5` | Fast | Default |
| `claude-opus-5-5` | Deep | Optional |

The server allowlist mirrors this list.

### 10.3 `POST /api/ai/turn` (backend)
- **Input:** the `AgLlmRequest` JSON. **Output:** `text/event-stream` of AG-UI events (`TEXT_MESSAGE_*`, `TOOL_CALL_*`), then a final `complete` event carrying `{ status, output, usage }`. `claudeAdapter.ts` turns that into `{ stream, complete }`.
- **Translation:**

  | Studio request | Claude Messages API |
  |---|---|
  | `instructions` | `system` |
  | `tools[].parameters` | `tools[].input_schema` |
  | `function_call` items | assistant `tool_use` blocks |
  | `function_call_output` items | user `tool_result` blocks |
  | `model.id` | `model` |

  Load the **claude-api** skill before implementing this, for current streaming and tool-use details.
- **Guards:**
  - model allowlist
  - tool-name allowlist (Studio's documented tools plus `trace_lineage` and `verify_chain`). Any other name is refused with 400.
  - a cap on `max_tokens`
  - a simple per-process rate limit
  - no key: `GET /api/health` reports `ai: false` and the UI hides the Copilot, with an "AI off" chip
- **Tests:**
  - `test_ai_turn_rejects_unknown_model`
  - `test_ai_turn_rejects_money_tools`, which sends a tool named `capture_order` and expects 400
  - `test_ai_turn_translates_tool_results` (recorded fixture)
  - `test_ai_key_never_in_response`
- **Stretch, AI replay fixtures:** with `REPLAY_MODE=true`, return recorded event streams keyed by the request hash. The demo prompts then build the same widgets in every take.

### 10.4 Guardrail story for the pitch
"Studio agents can read data and build widgets. None of them has a tool that moves money, and our proxy refuses any tool outside the allowlist. Every money action goes through the API and the four-factor firewall." It's the same deterministic-money rule as the rest of the system, now applied to the dashboard agents.

---

## 11. Phase-by-phase UI plan (alongside doc 10)

```text
            Sun1 | Mon2 Tue3 Wed4 Thu5 | Fri6 Sat7 | Sun8 Mon9 | Tue10 | Wed11 | Thu12
UI-0 found. ████ |                     |           |           |       |       |      doc 10 Phase 0 tail
UI-1 run      ░░ | █████████████████   |           |           |       |       |      doc 10 Phase 1 (1b live PayPal)
UI-2 studio      |      ░░░░░░████████ | █████████ |           |       |       |      doc 10 Phase 2 (starts on replay)
UI-3 defend      |                     |      ████ | █████████ |       |       |      doc 10 Phase 3
UI-4 polish      |                     |           |      ████ | ██▌   |       |      doc 10 Phase 4 · freeze Tue 18:00
UI-5 present     |                     |           |           |   ███ | █████ |      doc 10 Phase 5
```

### UI-0: Foundation (Sun Nov 1 – Mon Nov 2), about half a day

**Goal:** everything later inherits the look. Studio risk R5 is retired early.

| ID | Task | Files | Done when |
|---|---|---|---|
| UI-0.1 | Tokens (§4.2) in `index.css`, Tailwind `@theme inline` mapping, `setTheme()` that syncs `data-theme` and `data-ag-theme-mode` | `src/index.css`, `src/app/theme.ts` | The toggle switches the whole app in both themes, and the choice survives a reload |
| UI-0.2 | App shell: brand, hash nav, mode badge, chain badge, theme toggle. Page `<title>` "PactGuard AI" and favicon. | `src/app/AppShell.tsx`, `src/app/useHashRoute.ts`, `index.html`, `public/` | All three routes render. Mission Control shows the existing flow unchanged. |
| UI-0.3 | Primitives (§4.6). Move existing components onto `Card`, `Badge`, `Stat`, `Money`, `Hash` and `Button` (mechanical, no redesign). | `src/ui/*`, `src/features/*` | No raw palette classes left in `features/`. `npm run build` and `npm run lint` pass. |
| UI-0.4 | **AG Studio spike.** Install `ag-studio@3.0.0` and `ag-studio-react@3.0.0`. Lazy `#/studio` route. Mount over `/api/studio/rows` with `pactguardTheme`, one `grid` and one `value` widget. Licence from `VITE_AG_STUDIO_LICENSE`, with the watermark acceptable until B-6. Answer the §6.11 items you can. | `src/studio/CommandCenter.tsx`, `src/studio/theme.ts`, `frontend/.env.example` | Studio renders the run's rows in light and dark. Doc 09 B-6 is updated. |
| UI-0.5 | Fonts (Inter, JetBrains Mono) and `lucide-react` icons | `index.html`, `src/ui/*` | Hashes render in mono and money in tabular figures |

**Exit:** the existing Phase 1 flow runs inside the new shell in both themes, and Studio shows live run rows.

### UI-1: Mission Control (alongside doc 10 Phase 1, to Thu Nov 5)

**Goal:** a judge can follow mandate → market → negotiation → firewall → PayPal → receipt without anyone narrating.

| ID | Task | Needs | Done when |
|---|---|---|---|
| UI-1.1 | Two-column layout (§5.2). A sticky Mandate card shows a summary, with an edit mode that holds the current `MandateForm`. | — | Matches the wireframe at 1280 px. Stacks below 1024 px. |
| UI-1.2 | **Stage Rail** from SSE `stage`/`event` | SSE events | Stages light up in order during a replay run. A refused stage turns red. |
| UI-1.3 | **Mandate Ruler** component (shared with W1) | Run snapshot | Webcams fall in the auto zone, monitors in approval, the attack ✕ beyond the cap |
| UI-1.4 | **Firewall Checkpoint** drawer: four gates animate, stopwatch, route stamp, Approve/Reject (⏎ / Esc), 409 guard banner | approve/reject endpoints | Approving the monitors resumes the run. A BLOCKED item can't be approved, and the guard name is shown. |
| UI-1.5 | **PayPal button** (`@paypal/react-paypal-js`, live) wired to `/prepare` and `/capture`, plus the **Decide-and-Prove receipt**. Replay keeps the one-click path. Don't restyle PayPal's button. | doc 10 1b | A real sandbox order ID is shown on the receipt (doc 10 Phase 1 exit) |
| UI-1.6 | **Negotiation race lanes** with the baseline line, schema-gate stamp and commitment seal | `negotiated` event | The dropped seller and the cancelled runner-up are both visible at a glance |
| UI-1.7 | **Attack Theatre**: payload with the injected span highlighted, BLOCKED stamp, latency. Emits `pg:attack-blocked` (used by UI-2.10). | `/attack` | Under 1 ms is shown, and the reasons are listed |
| UI-1.8 | **Event ticker** replaces `Timeline`: `aria-live="polite"`, filter by stage, expand to the full log | SSE | The full log is still reachable. The ticker never grows the page. |
| UI-1.9 | Market cards (image, merchant, delta vs baseline, "terms hidden", allowlist chip) | `discovered` event | The existing table becomes cards. Keep the table view behind a toggle. |

**Exit:** doc 10's Phase 1 exit, plus the beats in §2.2 rows 1–4 work in both themes.

### UI-2: Command Center (alongside doc 10 Phase 2, Tue Nov 3 – Sat Nov 7)

**Goal:** a curated, themed, multi-page AG Studio report over our data, three or more custom widgets, and a Copilot that builds widgets by delegating to the built-in agents.

| ID | Task | Needs | Done when |
|---|---|---|---|
| UI-2.1 | `GET /api/studio/sources` (§8), new columns and tests. `seed_history.py` (doc 10 2a). | Backend | Tests green. Seeded plus live rows come back. |
| UI-2.2 | Studio data definition: formats, relationships, calendar, expressions, descriptions | UI-2.1 | Studio's field list shows friendly names. The relationships let filters on one table affect the related ones. |
| UI-2.3 | Curated `initialState` (five pages, §5.3), page titles, save to `localStorage`, "↺ Curated", Present/Edit toggle | UI-2.2 | A reload keeps the user's edits, and Reset restores the curated report |
| UI-2.4 | Full Studio theme: token-mapped params for light and dark, chart palette, fonts | UI-0.4 | Studio and Mission Control look like one product in both themes |
| UI-2.5 | **W1 Mandate Ruler, W2 Savings Dumbbell, W3 Lineage Chain** (§9) | UI-2.2 | Each widget has four states, cross-filter (W3 receives only), AI metadata, and appears in the "PactGuard" menu |
| UI-2.6 | `claudeAdapter.ts` plus `POST /api/ai/turn` with both allowlists and tests (§10.3) | `ANTHROPIC_API_KEY` | A built-in Lead run adds a widget through Claude |
| UI-2.7 | **Copilot** (primary) delegating to the built-ins and the **Auditor**. Custom tools `trace_lineage` and `verify_chain`. Prompt starters and model list. | UI-2.6 | "Savings by supplier, highlight blocked attempts" builds a widget on screen. The handoffs show in the chat panel. |
| UI-2.8 | Lineage drawer in Mission Control (click a deal or grid row → ledger timeline) and the **Mandate v1 → v2 diff** | `GET /api/runs/{id}/calibration` | Doc 10 Phase 2 exit items |
| UI-2.9 | **W4 Firewall Flow** | UI-2.5 | The Sankey cross-filters the Firewall page |
| UI-2.10 | **Sentinel** triggered by `pg:attack-blocked`, building the Incidents page, with a fallback when there's no key | UI-2.7, UI-1.7 | Simulating an attack, then opening the Command Center, shows the new incident widget |
| UI-2.11 | W5 Trust scoreboard | `suppliers` | — |
| UI-2.12 | WebMCP read-only bridge | Chrome 149+ flag | A browser agent can query the dashboard |
| UI-2.13 | AI replay fixtures (§10.3) | UI-2.6 | Demo prompts build the same widgets offline |

**Exit:** doc 10's Phase 2 exit, plus §2.1's table holds for every Must row.

> **Status (2026-11-12).** Built: the data definition, a curated six-page report, the theme, the Claude adapter and proxy (UI-2.6), the assistant with prompt starters, the lineage drawer and mandate diff (UI-2.8). Not built: the custom widgets W1 to W5 (UI-2.5, UI-2.9, UI-2.11), the Sentinel (UI-2.10), WebMCP (UI-2.12), AI replay fixtures (UI-2.13), `localStorage` persistence and the curated reset (part of UI-2.3), and the `GET /api/studio/sources` endpoint of §8.

### UI-3: Defend and Pay out (alongside doc 10 Phase 3, Sat Nov 7 – Mon Nov 9)

| ID | Task | Needs | Done when |
|---|---|---|---|
| UI-3.1 | Disputes desk with the triage queue and **DisputeCard** (§5.4) | `GET /api/disputes`, `/evidence`, `/submit` | The real sandbox dispute ID is shown. Submit needs a confirmation. |
| UI-3.2 | Evidence PDF preview | `/evidence` PDF | The PDF renders inline. Missing records are listed. |
| UI-3.3 | **Payout gate**: two locks, blocked → released, gross-to-net bar labelled "fee rate illustrative" | `release_payout` endpoint | Doc 10 Phase 3 exit: blocked, then released, on screen |
| UI-3.4 | Webhook inbox feed with "verified" and "duplicate ignored" chips | `POST /api/webhooks/paypal` + a list endpoint | A duplicate event shows as ignored |
| UI-3.5 | Studio **Defend** page: `disputes` and `payouts` sources, win-odds gauge, payouts chart. Stage 5 and 6 scripted controls ("simulate carrier update", the NW 1001 forensics flags). | Phase 3 data | Defend page in the curated report |
| UI-3.6 | Nudge scoreboard for overdue receivables (`s07.nudge_overdue`), friendly tone | — | — |

### UI-4: Polish sweep (alongside doc 10 Phase 4, Mon Nov 9 – Tue Nov 10, 18:00)

No new layouts. Work through §13.2 and fix everything it finds.

| ID | Task | Done when |
|---|---|---|
| UI-4.1 | States audit: empty, loading (`Skeleton`) and error (`ErrorBanner` + retry) on every screen and widget. Recover a run after refresh, and handle an unknown run ID. | No blank or stuck screen in any state |
| UI-4.2 | Accessibility: AA contrast for every token pair, visible focus, keyboard-only run-through (mandate → approve → pay), `aria-live` ticker, labelled SVG | A keyboard-only run-through completes the whole demo |
| UI-4.3 | Responsive check at 1440, 1280, 1024 and 390 px. Studio keeps `minWidth` 720 with horizontal scroll on phones. | No page-level horizontal scroll on Mission Control |
| UI-4.4 | Performance: lazy Studio, check the bundle split, memoise SSE lists, cap ticker length | Mission Control's first load excludes Studio's chunk |
| UI-4.5 | Copy and honesty labels: consistent route wording; "simulated seller", "seeded history", "illustrative fee" and "REPLAY" everywhere they apply | The doc 10 §2.3 rule 5 audit passes |
| UI-4.6 | Meta: title, favicon, OG image, footer listing the sponsor tools used | — |
| UI-4.7 | Served by FastAPI on Render: asset paths, SPA fallback for the hash routes, health badge | The public URL behaves like local |

### UI-5: Present and capture (alongside doc 10 Phase 5, Tue Nov 10 – Wed Nov 11)

| ID | Task | Done when |
|---|---|---|
| UI-5.1 | **Present mode** (`?present=1`): base font 112.5%, dev controls hidden, Studio in view mode, hotkeys `→` (next beat), `A` (attack), `T` (theme), `C` (Copilot) | Every take of the full arc is identical in replay |
| UI-5.2 | Screenshot set for Devpost: each screen in light and dark, plus the Copilot mid-build | Images in `docs/media/` |
| UI-5.3 | Rehearse the beats from §2.2 against doc 08's script, record in replay, and cut in the live proof clips | The video matches the README claims |

---

## 12. Task tracker

Status values: `todo`, `doing`, `done`, `cut`. Update this table in the same change as the work.

| ID | Task | Pri | Status |
|---|---|---|---|
| UI-0.1 | Tokens, Tailwind mapping, theme switch | Must | todo |
| UI-0.2 | App shell and hash routes | Must | todo |
| UI-0.3 | Primitives and migration | Must | todo |
| UI-0.4 | AG Studio spike (closes B-6 / R5) | Must | done |
| UI-0.5 | Fonts and icons | Should | todo |
| UI-1.1 | Mission Control layout | Must | todo |
| UI-1.2 | Stage Rail | Must | todo |
| UI-1.3 | Mandate Ruler component | Must | todo |
| UI-1.4 | Firewall Checkpoint drawer | Must | todo |
| UI-1.5 | PayPal button and receipt | Must | todo |
| UI-1.6 | Negotiation race lanes | Should | todo |
| UI-1.7 | Attack Theatre | Should | todo |
| UI-1.8 | Event ticker | Should | todo |
| UI-1.9 | Market cards | Could | todo |
| UI-2.1 | `/api/studio/sources` and tests | Must | todo |
| UI-2.2 | Studio data definition | Must | todo |
| UI-2.3 | Curated report, save/reset, Present/Edit | Must | todo |
| UI-2.4 | Studio theme (light and dark) | Must | todo |
| UI-2.5 | W1, W2, W3 custom widgets | Must | todo |
| UI-2.6 | Claude adapter and `/api/ai/turn` | Must | todo |
| UI-2.7 | Copilot, Auditor and custom tools | Must | todo |
| UI-2.8 | Lineage drawer and mandate diff | Must | todo |
| UI-2.9 | W4 Firewall Flow | Should | todo |
| UI-2.10 | Sentinel and the Incidents page | Should | todo |
| UI-2.11 | W5 Trust scoreboard | Could | todo |
| UI-2.12 | WebMCP bridge | Could | todo |
| UI-2.13 | AI replay fixtures | Could | todo |
| UI-3.1 | Disputes desk and DisputeCard | Must | todo |
| UI-3.2 | Evidence PDF preview | Should | todo |
| UI-3.3 | Payout gate | Must | todo |
| UI-3.4 | Webhook inbox feed | Should | todo |
| UI-3.5 | Studio Defend page and scripted controls | Should | todo |
| UI-3.6 | Nudge scoreboard | Could | todo |
| UI-4.1 | States audit | Must | todo |
| UI-4.2 | Accessibility pass | Must | todo |
| UI-4.3 | Responsive pass | Must | todo |
| UI-4.4 | Performance pass | Should | todo |
| UI-4.5 | Copy and honesty labels | Must | todo |
| UI-4.6 | Meta and footer | Should | todo |
| UI-4.7 | Render serving check | Must | todo |
| UI-5.1 | Present mode | Must | todo |
| UI-5.2 | Screenshot set | Must | todo |
| UI-5.3 | Rehearse and record | Must | todo |

---

## 13. Definition of done and polish checklist

### 13.1 Every UI task
- [ ] Uses tokens and primitives only. No new raw palette classes and no hard-coded hex values outside `index.css`.
- [ ] Correct in **light and dark**.
- [ ] Has empty, loading and error states. Guard refusals (409) show the guard's name.
- [ ] Keyboard reachable with a visible focus ring. Icons and SVGs have labels.
- [ ] Works in **replay mode**, and `make test` stays green (doc 10 §2.3 rule 2).
- [ ] Anything simulated, seeded or illustrative carries its label.
- [ ] `npm run build` and `npm run lint` pass.
- [ ] Checked in the browser preview, with a screenshot in the PR or commit notes.
- [ ] Tracker status updated in §12. Any §6.11 item answered is ticked here.

### 13.2 AG's dashboard checklist ("Grids + Charts != Dashboards"), mapped to our build

| Capability | How we cover it | Task |
|---|---|---|
| Layout | Curated five-page `initialState` with deliberate spans | UI-2.3 |
| Global filters | `date-filter` and route `button-filter` on every page | UI-2.3 |
| Cross-filtering | Built-in highlight, plus W1, W2 and W4 emitting and W3 receiving | UI-2.5 |
| Serialisable state | Saved to `localStorage`, plus "↺ Curated" | UI-2.3 |
| Edit and view modes | Present/Edit toggle | UI-2.3 |
| Config UI | Custom widget `form` options (thresholds on W1) | UI-2.5 |
| Calculated fields | `savings_rate`, `auto_rate`, `block_rate` | UI-2.2 |
| AI | Copilot, Auditor and Sentinel on Claude | UI-2.6–2.10 |
| Accessibility and keyboard | Studio built-in, plus our SVG widgets' focus and labels | UI-4.2 |
| Time bucketing | Calendar on `created_at` | UI-2.2 |
| Dark mode | A single switch drives both our tokens and Studio's mode | UI-0.1, UI-2.4 |
| Undo and redo | Studio built-in. Shown once in the Edit beat. | UI-2.3 |
| PDF export | **(verify)** that it's available in 3.0.0. If so, an "Export report" button. | UI-4.6 |

---

## 14. Risks, fallbacks, cut order

| # | Risk | Likelihood | Impact | Fallback |
|---|---|---|---|---|
| U1 | The AG Studio licence (B-6) arrives late | Closed | — | Closed 2026-11-01. The trial licence is installed and valid until 2026-12-16. |
| U2 | The Claude adapter takes longer than planned (Responses-shaped items) | Medium | High (AG agent criterion) | Copy the item handling from the boilerplate's `openai-adapter.ts`. Get the built-in Lead working first, then add ours. Last resort: drop the agent beat per doc 10's cut order and keep the widgets and theme. |
| U3 | Tailwind preflight clashes with Studio CSS | Medium | Medium | `themeCssLayer`. Scope Studio under its own container. Single-class selectors. |
| U4 | Route colours can't be controlled in built-in charts | Medium | Low | Route-coloured views live in W1 and W4, and built-in charts use the neutral palette (§4.2) |
| U5 | Studio bundle slows Mission Control | Low | Medium | Lazy route (UI-0.4) |
| U6 | An agent build in the video goes wrong | Medium | Medium | AI replay fixtures (UI-2.13), or record the beat until it's clean |
| U7 | UI scope eats Phase 1 time | Medium | High | The cut order below. Phase 1 exit criteria come before any Should item. |

**Cut order, first to drop:** UI-2.12 WebMCP → UI-2.11 W5 → UI-3.6 Nudge → UI-2.13 AI fixtures → UI-1.9 market cards → UI-2.9 W4 → UI-2.10 Sentinel auto-trigger (keep it as a manual prompt starter) → UI-1.6 race lanes (keep the table) → the ⌘K palette.

**Never cut:**
- the UI-0 foundation
- Mission Control's approval and PayPal flow
- the curated Studio report with W1–W3 and the theme
- the Copilot delegating to the built-ins
- the honesty labels

---

## 15. Sources (read 2026-11-01)

- AG Studio docs (React, 3.0.0):
  - [Quick Start](https://www.ag-grid.com/studio/react/quick-start/), [Custom Widgets](https://www.ag-grid.com/studio/react/custom-widgets/), [Data](https://www.ag-grid.com/studio/react/data/), [Theming](https://www.ag-grid.com/studio/react/theming/), [State](https://www.ag-grid.com/studio/react/state/), [Modes & Layout](https://www.ag-grid.com/studio/react/modes-layout/), [Studio Properties](https://www.ag-grid.com/studio/react/studio-properties/), [Compatibility](https://www.ag-grid.com/studio/react/compatibility/), [Licence](https://www.ag-grid.com/studio/react/licence-install/)
  - [Agent overview](https://www.ag-grid.com/studio/react/ai-agents/), [Built-in agents](https://www.ag-grid.com/studio/react/ai-builtin-agents/), [Direct LLM runner](https://www.ag-grid.com/studio/react/ai-direct-llm-runner/), [Client tool runner](https://www.ag-grid.com/studio/react/ai-client-tool-runner/), [Custom agents](https://www.ag-grid.com/studio/react/ai-custom-agents/), [Tools](https://www.ag-grid.com/studio/react/ai-tools/), [Chat UI](https://www.ag-grid.com/studio/react/ai-chat-ui/), [AI context](https://www.ag-grid.com/studio/react/ai-context/), [WebMCP](https://www.ag-grid.com/studio/javascript/ai-webmcp/)
  - Appending `.md` to any docs URL returns a Markdown copy, which is handy for agents. The full index is at [llms.txt](https://www.ag-grid.com/studio/llms.txt).
- Blog posts:
  - [Introducing the Studio Agent Framework](https://www.ag-grid.com/blog/introducing-the-ag-studio-agent-framework/)
  - [Who Owns the Harness?](https://www.ag-grid.com/blog/who-owns-the-harness/)
  - [WebMCP in AG Studio dashboards](https://www.ag-grid.com/blog/webmcp-in-ag-studio-dashboards/)
  - [1 prompt, 88 seconds](https://www.ag-grid.com/blog/1-prompt-88-seconds-i-added-a-new-chart-type-to-ag-studio-dashboard/)
  - [Grids + Charts != Dashboards](https://www.ag-grid.com/blog/grids-charts-dashboards/)
  - [2026 Launch Week](https://www.ag-grid.com/blog/2026-ag-studio-launch-week/)
  - [Figma Design System](https://www.ag-grid.com/blog/introducing-ag-studio-figma-design-system/)
  - [From Embedded Dashboards to Programmable Analytics](https://www.ag-grid.com/blog/from-embedded-dashboards-to-programmable-analytics/)
  - [Hackathon: PayPal and AG Studio](https://www.ag-grid.com/blog/hackathon-paypal-and-ag-studio/)
- Code: [PayPal + AG Studio boilerplate](https://github.com/paypaldev/hackathon-paypal-ag-grid-boilerplate) (Next.js 16; `app/dashboard/studio/{data,initial-report,theme,ai,openai-adapter}.ts` are the files to copy patterns from).
- Prize page: [Devpost, AG Grid](https://paypalaihackathon.devpost.com/details/aggrid).
