# Section 7: Top 3 Recommendations (Detailed Briefs)

This document provides complete, implementation-ready specifications for the **top three candidate projects**:
1. **PactGuard AI** *(Autonomous Procurement, Multi-Agent Negotiation & Spend-Mandate Control Plane)*
2. **AegisPay** *(Autonomous PayPal Dispute Defense, Fulfillment Attestation & Triage OS)*
3. **ChronoPay** *(Deliverable-Verified Milestone Escrow, Gantt Rescheduler & Friendly Nudge OS)*

---

## 🥇 RECOMMENDATION #1: PactGuard AI

### Project Identity
* **Project Name:** **PactGuard AI** — *Autonomous Procurement, Multi-Agent Negotiation & Spend-Mandate Control Plane for PayPal*
* **One-Line Pitch:** PactGuard AI lets businesses and consumers delegate shopping and B2B procurement to autonomous AI agents that discover real products via **Channel3**, bargain down supplier quotes in parallel, enforce cryptographic **Auto-Purchase Spend Mandates**, and settle atomically via **PayPal** inside a live **AG Studio** command center.

### Problem Statement
Agentic commerce is broken at three critical junctions:
1. **Discovery & Terms Opacity:** 18.9% of merchant sites block bots and >90% hide machine-decidable all-in totals and return terms ([`arXiv:2610.17378`](https://arxiv.org/abs/2610.17378v1)).
2. **Irrational Negotiation:** Unconstrained LLM agents get stuck in polite loops, over-concede, or accidentally double-commit across parallel suppliers ([`arXiv:2610.11542`](https://arxiv.org/abs/2610.11542v3), [`arXiv:2610.06017`](https://arxiv.org/abs/2610.06017v1)).
3. **Unguarded Payment Execution:** Official toolkits like [`paypal/agent-toolkit`](https://github.com/paypal/agent-toolkit) expose `create_order`, `pay_order`, and `send_invoice` with **zero built-in spend bounds, human-in-the-loop gates, or per-call idempotency** ([Issue #95](https://github.com/paypal/agent-toolkit/issues/95), [Issue #98](https://github.com/paypal/agent-toolkit/issues/98), [Issue #105](https://github.com/paypal/agent-toolkit/issues/105)), causing LLMs to overreach and commit funds without permission ([`arXiv:2610.29216`](https://arxiv.org/abs/2610.29216v1)).

### Target User
SMB operations/procurement managers, event/office planners, and developers deploying autonomous purchasing agents on PayPal.

### Proposed Solution
An end-to-end **Agentic Commerce & Governance Platform** combining:
1. **Channel3 Product & Readiness Discovery:** Queries **Channel3 API/MCP** (100M+ real products) to retrieve normalized prices, variants, availability, and "Decide & Prove" return-policy readiness scores.
2. **Constitutional Multi-Agent Negotiation Arena:** For bulk/B2B sourcing, spawns 3 concurrent Buyer-to-Seller negotiation threads governed by a deterministic **Alternating-Offers Schema Gate & CANO Optimizer** (`arXiv:2610.06017`) that bargains down unit price and locks the winning quote with a SHA-256 commitment digest.
3. **4-Factor Auto-Purchase Mandate Firewall (`arXiv:2610.29216` + `arXiv:2610.22899`):** Evaluates every PayPal mutation against **Warrant** (spec match), **Reversibility** (return window), **Price Norm** (discount vs. retail benchmark), and **Urgency/Budget**, routing the transaction into `AUTO_SETTLE`, `HUMAN_APPROVAL_REQUIRED`, or `BLOCKED` with SHAP/feature attribution bars.
4. **Idempotent PayPal Settlement & AG Studio Command Center:** Executes approved transactions via **PayPal Orders v2, Invoicing v2, and Payouts APIs** (with per-call `PayPal-Request-Id` idempotency and penny-exact tax validation), visualized in real time inside an interactive **AG Studio** dashboard with natural-language widget generation.

### Core User Journey
1. **Set Mandate:** User defines a Procurement Mandate (e.g., *"Equip a 5-person startup office with monitors, webcams, and mics under \$2,200; auto-approve items <\$300 with 30-day returns; require 1-click approval above \$300"*).
2. **Discover & Benchmark:** PactGuard queries **Channel3 API** for real retail baseline prices and product specs.
3. **Parallel Negotiation:** For the 5-monitor bulk line item, PactGuard launches 3 concurrent supplier agent negotiations in a live visual arena, bargaining the bundle down from \$1,450 to \$1,180 in 3 deterministic rounds.
4. **Mandate Firewall & Execution:**
   * *Transaction A (\$180 Webcams):* Passes all 4 Auto-Purchase checks -> **Auto-executes** via PayPal Orders API (`CREATED` -> `CAPTURED`) with a sealed "Prove" terms certificate.
   * *Transaction B (\$1,180 Negotiated Monitor Contract):* Exceeds the \$300 auto-commit threshold -> Pauses in `HUMAN_APPROVAL_REQUIRED` -> User clicks **"Approve & Pay with PayPal"** -> Generates & settles the official PayPal Order/Invoice.
   * *Transaction C (Simulated adversarial prompt injection attempting a \$900 unauthorized payout):* Intercepted and **Blocked** by the Mandate Firewall.
5. **Live FinOps Dashboard:** User asks the **AG Studio Agent** *"Show me savings by supplier vs. retail baseline and mandate risk scores,"* and AG Studio dynamically builds the cross-filtering widgets.

### System Architecture
```text
[React + TypeScript Frontend]
 ├── AG Studio Self-Serve Analytics & Studio Agent Framework (Live Spend, Savings & Risk Grid)
 ├── Multi-Agent Negotiation Arena UI (3 Parallel Supplier Threads + Turn-by-Turn Diff)
 └── Mandate Firewall & PayPal Checkout / Approval Drawer (PayPal JS SDK v6)
        │ (REST / WebSockets / SSE)
[FastAPI Backend (Deployed on Render + Render Workflows)]
 ├── Discovery Engine ──────► Channel3 API & MCP Server (100M+ Normalized Products)
 ├── Negotiation Engine ────► 3 Parallel Seller Agents + Constitutional Schema Gate (OpenAI/Claude)
 ├── Mandate Firewall ──────► 4-Factor Auto-Purchase Scorer (Warrant, Reversibility, Price, Budget)
 │                            + Canonical SHA-256 Digest & Per-Call PayPal-Request-Id Generator
 └── PayPal Settlement Layer ► @paypal/agent-toolkit + APIMatic-Verified PayPal Python/TS SDK
                              (Orders v2, Invoicing v2, Payouts, Webhooks + Sealed Audit SQLite/Postgres)
```

### Required APIs / Models / Datasets
* **PayPal:** PayPal Agent Toolkit (`paypal-agent-toolkit` / `@paypal/mcp`), PayPal Orders v2 API, PayPal Invoicing v2 API, PayPal Payouts API, PayPal JS SDK v6 (Sandbox).
* **Sponsor Tools:** **Channel3 API/MCP** (`PAYPAL-HACKATHON-2026` promo code for 20,000 free credits), **AG Studio & Studio Agent Framework** (45-day trial), **APIMatic Context Plugin for PayPal**, **Render** (web service + Render Workflows).
* **Models:** `gpt-4o` / `gpt-4o-mini` or `claude-3-5-sonnet` (via API) + lightweight local `scikit-learn` / XGBoost 4-factor mandate scorer.

### Tech Stack
Python 3.11 + FastAPI + SQLite/PostgreSQL + React 18 + TypeScript + Vite + Tailwind CSS + AG Studio (`@ag-grid-enterprise` / Studio trial) + PayPal SDKs.

### Feature List
* **Must-Have (MVP):**
  1. Live **Channel3 API** search & retail baseline price enrichment.
  2. 3-Supplier **Constitutional Multi-Agent Negotiation** loop with deterministic 3-turn convergence and savings calculation.
  3. **4-Factor Auto-Purchase Mandate Firewall** (`AUTO_SETTLE` vs. `CONFIRM_FIRST` vs. `REJECT`) with per-call `PayPal-Request-Id` idempotency and tax-rounding verification.
  4. Real **PayPal Sandbox Orders v2 & Invoicing v2** execution + verifiable receipt links.
  5. **AG Studio** dashboard with custom Mandate/Savings widgets and Studio Agent natural-language querying.
* **Nice-to-Have:**
  1. Sealed **"Get In, Decide, Prove" PDF Certificate** attached to every PayPal transaction for future dispute immunity.
  2. Adversarial "Red-Team Prompt Injection" test button in the UI to prove the firewall blocks unauthorized spend in real time.
* **Stretch Features:**
  1. **Bryntum Timeline** view showing scheduled delivery dates and net-30 payment tranches.
  2. Slack/Discord human-approval webhook via **Zapier MCP**.

### Demo Script for 3-Minute Presentation
* **0:00–0:25 (The Hook & Verified Pain):** Show [`paypal/agent-toolkit` Issue #95](https://github.com/paypal/agent-toolkit/issues/95) on screen: *"Today, giving an AI agent access to PayPal means choosing between a powerless chatbot that can't transact, or an unguarded agent that can hallucinate, overpay suppliers, and drain your account without a human gate. Meet PactGuard AI."*
* **0:25–1:05 (Channel3 Discovery + Parallel Agent Negotiation):** Type a procurement prompt: *"Source 5 studio kits for our remote team under \$1,500."* Watch PactGuard pull real retail benchmarks via **Channel3**, then launch 3 concurrent supplier negotiations side-by-side. Supplier B concessions drop the total by \$270 (18% savings) in 3 structured rounds, locked with a cryptographic commitment hash.
* **1:05–2:00 (The 4-Factor Mandate Firewall & Live PayPal Settlement):** Show the 3 line-item transactions hitting the Mandate Firewall:
  1. The \$140 accessories order scores `0.94` on the Auto-Purchase Line (`Warrant: High`, `30-day Returns`, `Below Price Norm`) and **auto-captures via PayPal Orders v2** with an idempotent `PayPal-Request-Id`.
  2. The \$1,120 bulk monitor order triggers a **Human-in-the-Loop Mandate Hold**. Click **"Approve & Pay with PayPal"**—watch the real PayPal Sandbox Order & Invoice generate and capture on screen.
  3. Click **"Simulate Prompt Injection Attack"**—watch the firewall block an unauthorized \$800 payout in `<10ms` with a visual SHAP risk explanation.
* **2:00–2:40 (AG Studio "Dashboard Without a Dashboard"):** Open the **AG Studio** command center. Type into the Studio Agent: *"Break down our negotiated savings by category and highlight any blocked agent attempts."* Watch AG Studio build the live cross-filtering charts and audit grid on the fly.
* **2:40–3:00 (Impact & Close):** Recap how PactGuard combines **PayPal Agent Toolkit**, **Channel3**, **AG Studio**, **APIMatic**, and **Render** to make agentic commerce safe, rational, and ready for production.

### Evaluation Plan
* **Mandate Alignment Accuracy:** Measure precision/recall of the 4-factor gate across 50 synthetic purchase scenarios (target: 100% block rate on over-budget/non-refundable/injected requests).
* **Negotiation Efficiency:** Measure average price reduction (%) vs. Channel3 retail baseline and turn count across 20 runs (target: 12–18% savings in $\le 3$ turns with 0 schema failures).
* **PayPal Payload Validity:** 100% pass rate on PayPal Sandbox Orders v2 & Invoicing v2 endpoints (zero `AMOUNT_MISMATCH` or duplicate capture errors).

### Risks and Mitigations
* *Risk:* LLM latency during 3 parallel negotiations slows down the live video. *Mitigation:* Run the 3 supplier calls concurrently via `asyncio.gather` using fast models (`gpt-4o-mini` / `claude-3-5-haiku`) and stream each turn over Server-Sent Events (SSE) so the UI animates immediately in `<4` seconds total.
* *Risk:* PayPal Sandbox intermittent slowness. *Mitigation:* Cache OAuth tokens proactively, use APIMatic-validated payloads, and build a live Sandbox + Deterministic Replay toggle for zero-fail judging.

---

## 🥈 RECOMMENDATION #2: AegisPay

### Project Identity
* **Project Name:** **AegisPay** — *Autonomous PayPal Dispute Defense, Fulfillment Attestation & Triage OS*
* **One-Line Pitch:** AegisPay protects online merchants and SaaS founders from illegitimate chargebacks and dispute spam by sealing cryptographic fulfillment proofs at checkout, triaging incoming disputes on a **Bryntum Scheduler**, and autonomously compiling and submitting forensic PDF evidence packets to the **PayPal Disputes API**—with zero 25% commission fees.

### Problem Statement
When a buyer files an "Item Not Received" (INR) or "Significantly Not as Described" (SNAD) dispute on PayPal—or when a startup is hit by a wave of bot disputes ([HN #44176510](https://news.ycombinator.com/item?id=44176510))—merchants face a brutal dilemma: spend 2 hours manually stitching together server access logs, shipping receipts, and chat transcripts, forfeit the money, or pay **25% of recovered revenue** to Chargeflow. Worse yet, PayPal's own [`paypal/agent-toolkit`](https://github.com/paypal/agent-toolkit) only includes `accept_dispute_claim` (surrendering the dispute!) and completely lacks tools to compile and submit defense evidence (`provide-evidence`) or make counter-offers (`make-offer`).

### Target User
SaaS founders, digital goods creators, e-commerce merchants, and marketplaces using PayPal.

### Proposed Solution
1. **Pre-Dispute "Decide & Prove" Checkout Vault (`arXiv:2610.17378`):** At the moment of PayPal Checkout, AegisPay seals a SHA-256 **Fulfillment & Terms Attestation Record** (the exact product description, refund policy, buyer IP, download/access timestamps, and carrier tracking).
2. **Missing PayPal Agent Toolkit Dispute-Defense Extensions:** Built using **APIMatic Context Plugins for PayPal**, AegisPay adds the missing `provide_dispute_evidence`, `make_dispute_resolution_offer`, and `appeal_dispute` MCP tools to `paypal/agent-toolkit`.
3. **Autonomous RAG Evidence Compiler & PDF Brief Generator:** When a `CUSTOMER.DISPUTE.CREATED` webhook fires, AegisPay's agent queries order history, server/download telemetry, carrier tracking, and customer support transcripts, then synthesizes a structured, cited **Forensic Defense PDF** mapped to PayPal's exact `evidence_type` taxonomy (`PROOF_OF_FULFILLMENT`, `PROOF_OF_REFUND`, `CONTRACT`, `OTHER`).
4. **Bryntum Dispute Triage Scheduler + AG Studio Analytics:** Visualizes every open dispute across support agents on a **Bryntum Scheduler** (showing response deadlines, disputed dollar amounts, and AI evidence readiness—matching Bryntum's official Devpost prompt!) alongside an **AG Studio** dispute-intelligence dashboard.

### Core User Journey
1. **Simulate / Receive Dispute:** A buyer purchases a \$299 SaaS license or physical item via PayPal Sandbox, downloads the software (logged with IP & timestamp), and then files a `MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED` dispute.
2. **Automated Triage on Bryntum Scheduler:** The webhook lands in AegisPay; the agent calculates win probability (`89%`), assigns a 45-minute review block on the **Bryntum Dispute Triage Scheduler** before the PayPal deadline, and highlights any unallocated high-value deadlines in red.
3. **Forensic Brief Generation:** In `<10` seconds, the AI retrieves the sealed checkout terms, 14 server usage events, and the customer's onboarding chat log, generating a formatted 3-page PDF brief with embedded SHA-256 verification hashes.
4. **1-Click or Auto-Submit to PayPal Disputes API:** The merchant reviews the brief side-by-side and clicks **"Submit Evidence to PayPal"** (calling `POST /v1/customer/disputes/{id}/provide-evidence` + `send_Tracking`), transitioning the dispute status in real time.

### System Architecture
```text
[React + TypeScript Frontend]
 ├── Bryntum Scheduler ("Dispute Triage Board": Agent Rows, Deadlines, Evidence Readiness)
 ├── AG Studio Analytics Grid & Studio Agent (Win-Rate, Reason Breakdown, Saved Revenue)
 └── Forensic Evidence Inspector & Side-by-Side PDF Previewer
        │
[FastAPI Backend (Deployed on Render + Render Workflows)]
 ├── Checkout Attestation Vault ──► Seals Terms, IP Logs & Tracking via PayPal Tracking API
 ├── Multi-Source RAG Engine ─────► Queries Order DB, Access Logs & Support Chats (Elastic/SQLite)
 ├── Forensic PDF Compiler ───────► LLM Rebuttal Writer + ReportLab/WeasyPrint PDF Renderer
 └── PayPal Dispute Defense SDK ──► Extends paypal/agent-toolkit via APIMatic (provide-evidence,
                                    make-offer, accept-claim, webhooks)
```

### Feature List
* **Must-Have (MVP):**
  1. Checkout "Decide & Prove" telemetry sealer + PayPal Shipment/Fulfillment Tracking sync.
  2. Custom `provide_dispute_evidence` & `make_dispute_offer` MCP tools extending `paypal/agent-toolkit` (fixing the `accept_dispute_claim` gap).
  3. Automated PDF Evidence Packet generator combining order details, IP/usage logs, and chat transcripts.
  4. **Bryntum Dispute Triage Board (Scheduler)** showing agent timelines, deadlines, and readiness status.
  5. **AG Studio** financial recovery dashboard.

---

## 🥉 RECOMMENDATION #3: ChronoPay

### Project Identity
* **Project Name:** **ChronoPay** — *Deliverable-Verified Milestone Escrow, Gantt Rescheduler & Friendly Nudge OS*
* **One-Line Pitch:** ChronoPay turns client contracts into living **Bryntum Gantt** timelines where **PayPal Invoices and Payouts** are wired directly into project dependencies—using AI to verify deliverables before billing, automatically shifting deadlines when payments stall, and nudging overdue clients from an **AG Studio** scoreboard.

### Problem Statement
Freelancers, agencies, and software contractors face constant cash-flow anxiety: project timelines live in Jira/Gantt charts, deliverables live in GitHub/Figma/PDFs, and money lives in PayPal Invoicing. When a client pays a milestone late, downstream delivery dates aren't automatically adjusted; when work is finished, freelancers waste hours manually creating invoices, chasing overdue balances ([`r/freelance`](https://www.reddit.com/r/freelance/comments/ivipfs/i_asked_a_client_about_some_unpaid_invoices_what/)), and splitting payouts to subcontractors ([`paypal/agent-toolkit` PR #107](https://github.com/paypal/agent-toolkit/pull/107)).

### Proposed Solution
1. **AI SOW-to-Gantt & PayPal Invoice Series Generator:** Upload any PDF Statement of Work (SOW) or type a project brief; ChronoPay extracts milestones, acceptance criteria, and subcontractor splits, rendering a dependency-linked **Bryntum Gantt** board and creating real draft **PayPal Invoices** (with QR codes and conditional rules) for every tranche.
2. **AI Deliverable Verifier ("Proof-of-Work Before Invoice"):** When a contractor submits a deliverable (a GitHub PR link, deployed URL, or design PDF), an AI Evaluator checks it against the milestone's acceptance rubric, attaches a verification summary to the PayPal Invoice note, and dispatches the invoice via `send_invoice`.
3. **Event-Driven Gantt Rescheduler & Instant Subcontractor Payouts:** Listens to PayPal Webhooks (`INVOICING.INVOICE.PAID`, `PAYMENT.CAPTURE.DENIED`):
   * If a milestone payment is **overdue or fails**, the agent automatically blocks the dependent phase on the **Bryntum Gantt** chart and shifts downstream dates day-for-day.
   * The instant a client pays the PayPal Invoice, the agent unlocks the next Gantt phase and triggers an instant **PayPal Payouts API** split to any subcontractors assigned to that milestone!
4. **AG Studio "Friendly Nudge-Bot" Scoreboard:** Implements AG Grid's official Devpost idea—an **AG Studio** dashboard showing receivables health and a gentle, personality-driven AI Nudge-Bot that drafts warm reminders with embedded PayPal QR codes.

### Feature List
* **Must-Have (MVP):**
  1. PDF/Text SOW parser that auto-generates a **Bryntum Gantt** timeline + PayPal Draft Invoices.
  2. AI Deliverable Verifier that grades work against milestone criteria and triggers `send_invoice` + `generate_invoice_qr_code`.
  3. Agent-driven Gantt rescheduler that shifts dependent tasks when a PayPal invoice is unpaid/overdue.
  4. Instant subcontractor split execution via **PayPal Payouts API** upon invoice payment.
  5. **AG Studio** "Friendly Nudge-Bot" scoreboard with 1-click PayPal reminder execution.
