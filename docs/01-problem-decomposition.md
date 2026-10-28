# Section 1: Problem Decomposition

This document breaks the **PayPal AI Hackathon** topic into **8 concrete, high-impact sub-problems**, detailing the specific user groups affected, current workarounds, technical difficulty, hackathon feasibility, official track alignment, and the critical demo climax for each.

---

### Sub-Problem 1: Pre-Execution Governance, Spend Mandates & Idempotency for PayPal AI Agents
* **Problem Statement:** When AI agents are given access to payment tools via the [PayPal Agent Toolkit (`paypal/agent-toolkit`)](https://github.com/paypal/agent-toolkit) or [PayPal MCP Server](https://docs.paypal.ai/developer/tools/ai/mcp-quickstart), they lack built-in spend bounds, human-in-the-loop confirmation gates, tool-level read/write annotations, and per-call idempotency headers—meaning an LLM hallucination or retry loop can execute unauthorized or duplicate financial captures.
* **Who Experiences It:** Developers, fintech engineers, and businesses deploying autonomous shopping, procurement, or support agents on PayPal.
* **Why It Matters:** A single runaway agent loop or prompt injection on `pay_order`, `accept_dispute_claim`, or `create_refund` causes irreversible monetary loss. This is documented directly in [`paypal/agent-toolkit` Issue #95](https://github.com/paypal/agent-toolkit/issues/95), [Issue #98](https://github.com/paypal/agent-toolkit/issues/98), [Issue #105](https://github.com/paypal/agent-toolkit/issues/105), and [Issue #114](https://github.com/paypal/agent-toolkit/issues/114).
* **Current Workaround:** Developers either strip out all mutating tools (reducing the agent to a read-only chatbot) or hardcode brittle `if/else` wrapper scripts around every tool call.
* **Technical Difficulty:** Medium
* **Hackathon Feasibility:** **High** (clean middleware + policy engine + real PayPal Sandbox execution).
* **Alignment with Official Directions & Prizes:**
  * *Directions:* AI Agents or Automation (Primary), Business Solutions.
  * *Prizes:* **Best Use of Agentic Commerce (\$5k)**, **Best Use of PayPal + AI (\$5k)**, **Best Use of AG Grid (\$5k)** (live audit & policy telemetry dashboard).
* **Potential Demo Moment:** An autonomous procurement agent attempts three PayPal transactions: a \$15 approved SaaS renewal auto-executes via PayPal Orders API; a \$450 over-budget purchase is intercepted mid-flight by the cryptographic policy gate and triggers a 1-click UI/Slack human approval; and a prompt-injected refund attack is deterministically blocked with a live explainable risk trace.

---

### Sub-Problem 2: Merchant Chargeback & Dispute Evidence Compilation (Especially Digital Goods & "SNAD")
* **Problem Statement:** Merchants facing "Item Not Received" (INR) or "Significantly Not as Described" (SNAD) disputes—or waves of bot-driven dispute spam—must manually gather server logs, IP/download timestamps, chat transcripts, invoice PDFs, and carrier tracking, format them into strict multipart payloads, and submit them to the [PayPal Disputes API](https://developer.paypal.com/platforms/disputes/overview) before rigid deadlines.
* **Who Experiences It:** Digital goods/SaaS founders, e-commerce merchants, and freelancers using PayPal Checkout or Multiparty APIs.
* **Why It Matters:** Digital goods lack standard physical Seller Protection by default ([Reddit `r/paypal`](https://www.reddit.com/r/paypal/comments/dxnurx/how_to_prevent_chargebacks_on_digital_goods/)), Braintree/PayPal pre-arbitration policies penalize merchants ([HN #45993166](https://news.ycombinator.com/item?id=45993166)), and manual evidence compilation takes 1–3 hours per dispute while commercial tools like [Chargeflow](https://www.chargeflow.io/) take 25% of recovered revenue.
* **Current Workaround:** Manually taking screenshots of database logs, stitching PDFs together in Acrobat, and uploading them in the PayPal Resolution Center UI—or forfeiting claims under \$100.
* **Technical Difficulty:** Medium
* **Hackathon Feasibility:** **High** (PayPal Sandbox Disputes API + RAG over order/access logs + automated PDF evidence brief generation).
* **Alignment with Official Directions & Prizes:**
  * *Directions:* Business Solutions (Primary), AI Agents or Automation.
  * *Prizes:* **Best Use of PayPal + AI (\$5k)**, **Most Impactful (\$5k)**, **Best Use of Bryntum (\$1k x3)** (Bryntum's official Devpost page explicitly suggests a *"Dispute triage board (Scheduler)"*!).
* **Potential Demo Moment:** A live `CUSTOMER.DISPUTE.CREATED` webhook arrives; the AI agent queries server access logs + shipping data + customer chat history, compiles a cited 4-page forensic PDF defense brief, schedules the deadline on a Bryntum Dispute Triage Scheduler, and submits the evidence via PayPal's `provide-evidence` endpoint in 12 seconds.

---

### Sub-Problem 3: Deliverable-Verified Milestone Invoicing & Scope-Creep Protection for Freelancers/Agencies
* **Problem Statement:** Freelancers and agencies lose thousands of dollars to scope creep, late milestone payments, and clients withholding final payments, while clients fear paying upfront for unverified work; project schedules (Gantt/deadlines) and payment states ([PayPal Invoicing API](https://developer.paypal.com/invoicing/about)) live in completely disconnected tools.
* **Who Experiences It:** Freelancers, software contractors, creative agencies, and SMB service providers billing via PayPal Invoices.
* **Why It Matters:** Chasing unpaid invoices is one of the highest-frequency complaints on [`r/freelance`](https://www.reddit.com/r/freelance/comments/ivipfs/i_asked_a_client_about_some_unpaid_invoices_what/), and late milestone payments cascade into project timeline delays without automated enforcement.
* **Current Workaround:** Manually checking GitHub PRs/Figma links, copy-pasting line items into PayPal Invoices, sending awkward reminder emails, and manually shifting project dates in spreadsheets.
* **Technical Difficulty:** Easy–Medium
* **Hackathon Feasibility:** **High** (PayPal Invoicing API / Agent Toolkit + LLM contract/deliverable verifier + Bryntum Gantt/Scheduler).
* **Alignment with Official Directions & Prizes:**
  * *Directions:* Business Solutions, Money Movement Experiences, AI Agents or Automation.
  * *Prizes:* **Best Use of Bryntum (\$1k x3)** (Bryntum's Devpost page explicitly pitches *"Agency delivery board (Gantt): multi-client project timelines with payment tranches marked as dependencies"* and *"Agent-driven rescheduler"*!), **Best Use of AG Grid (\$5k)** (friendly *"Nudge-bot"* scoreboard).
* **Potential Demo Moment:** Upload a client PDF scope-of-work; the AI auto-generates a dependency-linked Bryntum Gantt schedule and draft PayPal Invoices for each milestone. When a GitHub PR / deliverable is submitted, the AI verifies completion against the contract rubric and dispatches the PayPal Invoice; when a simulated payment fails or is delayed via webhook, the agent automatically recalculates downstream Gantt dependencies and drafts a polite nudge.

---

### Sub-Problem 4: Cross-Merchant Agentic Discovery, Multi-Item Comparison & Unified PayPal Checkout
* **Problem Statement:** Consumer and B2B shopping agents can chat about products, but fail at cross-retailer product normalization (price, variants, real-time stock, return terms) and cannot seamlessly transition from multi-retailer discovery into a verified, single-approval PayPal payment flow.
* **Who Experiences It:** Everyday consumers, office managers, and event planners buying multi-item bundles (e.g., home office setup, party supplies, travel gear) on a budget.
* **Why It Matters:** As shown in the Oct 2026 benchmark [*Get In, Decide, Prove* (`arXiv:2610.17378`)](http://arxiv.org/abs/2610.17378v1), 18.9% of merchant sites block declared agent browsers outright and over 90% fail to expose machine-decidable all-in totals and return terms via scraping.
* **Current Workaround:** Opening 15 browser tabs, comparing specs manually in a spreadsheet, and completing separate checkouts.
* **Technical Difficulty:** Easy–Medium
* **Hackathon Feasibility:** **High** (Directly pairs **Channel3 API/MCP** for 100M+ normalized products with **PayPal Orders / Checkout SDK v6 / Agent Toolkit**).
* **Alignment with Official Directions & Prizes:**
  * *Directions:* Consumer Experiences, AI Agents or Automation.
  * *Prizes:* **Best Use of Channel3 (\$1,500)**, **Best Use of Agentic Commerce (\$5,000)**, **Best Demo Delivery (\$5,000)**.
* **Potential Demo Moment:** User tells the agent: *"Equip a podcast studio for two people under \$600 with at least 4.5-star ratings and free returns."* The agent queries **Channel3 MCP** across 25,000+ retailers, optimizes the bundle under budget, verifies return policies, and renders an instant interactive cart that settles in one click via **PayPal Checkout / Pay Later**.

---

### Sub-Problem 5: Autonomous B2B Vendor Negotiation & Spot-Procurement Settlement (Agent-to-Agent Commerce)
* **Problem Statement:** Small businesses sourcing wholesale inventory, freelance labor, or SaaS licenses waste hours negotiating quotes, volume discounts, shipping terms, and net-payment schedules across multiple vendors over email before manually issuing a purchase order and PayPal payment.
* **Who Experiences It:** E-commerce store owners, SMB procurement leads, and marketplace operators.
* **Why It Matters:** Academic benchmarks ([*Concurrency-Aware Procurement Negotiation*, `arXiv:2610.06017`](http://arxiv.org/abs/2610.06017v1); [*Constitutional Gating for Multi-Agent LLM Negotiation*, `arXiv:2610.11542`](http://arxiv.org/abs/2610.11542v3)) prove that unstructured LLM agents get stuck in polite loops, over-concede, or violate budget caps unless governed by a deterministic negotiation optimizer and constitutional schema gate.
* **Current Workaround:** Back-and-forth emails, phone calls, and manual PayPal invoice generation after a deal is verbally agreed.
* **Technical Difficulty:** Medium–Hard
* **Hackathon Feasibility:** **High** (if scoped as a live Buyer Agent negotiating concurrently against 3 simulated Seller Agents over MCP/A2A, settling the winning contract via PayPal Orders/Invoicing API).
* **Alignment with Official Directions & Prizes:**
  * *Directions:* AI Agents or Automation (*Devpost explicitly asks for: "two agents negotiating and settling a payment between themselves (agent-to-agent commerce)"*!).
  * *Prizes:* **Best Use of Agentic Commerce (\$5,000)**, **Most Creative (\$5,000)**, **1st Place (\$12,000)**.
* **Potential Demo Moment:** A split-screen visual arena where a Buyer Agent negotiates in parallel with 3 Supplier Agents (evaluating unit price, warranty, and delivery date), drops overpriced suppliers, locks in an 18% discount with Supplier B using a cryptographic commitment hash, and immediately generates and captures the settled PayPal Order.

---

### Sub-Problem 6: Multi-Party Receipt/Invoice Decomposition, FX Fee Transparency & Instant Payout Orchestration
* **Problem Statement:** Marketplaces, creator collectives, hackathons, and gig platforms struggle to ingest unstructured receipts/timesheets/invoices, calculate transparent currency-conversion and PayPal fee splits, reconcile 1099-K gross-vs-net discrepancies, and trigger batch payouts the instant work is verified.
* **Who Experiences It:** Gig/creator platform operators, international remote teams, nonprofit field coordinators, and group expense organizers.
* **Why It Matters:** PayPal's official `@paypal/agent-toolkit` lacked Payouts tools until community [PR #107 (Oct 4, 2026)](https://github.com/paypal/agent-toolkit/pull/107) highlighted that *"the toolkit lets an agent take money in (orders, invoices, subscriptions), but it can't pay anyone out."* Furthermore, international creators complain heavily on Reddit about opaque 4–5% FX spreads and gross-vs-net 1099-K reconciliation pain.
* **Current Workaround:** Exporting CSVs, running manual Excel formulas to deduct fees, and uploading batch CSV files to the PayPal Payouts dashboard.
* **Technical Difficulty:** Medium
* **Hackathon Feasibility:** **High** (Vision-LLM receipt/invoice parser + custom MCP Payouts tool calling PayPal Payouts REST API + AG Studio analytics grid).
* **Alignment with Official Directions & Prizes:**
  * *Directions:* Money Movement Experiences (Primary), Business Solutions, Social Impact Ideas.
  * *Prizes:* **Best Use of AG Grid (\$5,000)**, **Best Use of PayPal + AI (\$5,000)**.
* **Potential Demo Moment:** Drag-and-drop 5 messy contributor invoices/receipts in 3 currencies (USD, EUR, GBP) or a group dinner receipt; the Vision-LLM extracts line items, reconciles gross-to-net FX/fees inside an interactive **AG Studio** dashboard, and dispatches a real batch **PayPal Payouts API** transaction to all recipients in one click.

---

### Sub-Problem 7: Visually Homogeneous B2B Invoice Reconciliation & Duplicate/Fraud Detection
* **Problem Statement:** SMB finance teams receive hundreds of PDF vendor invoices that look nearly identical (same templates, recurring monthly line items) and must cross-check them against purchase orders, delivery receipts, and historical PayPal transactions to prevent duplicate payments or subtle invoice-doctoring scams.
* **Who Experiences It:** SMB bookkeepers, accounts payable (AP) clerks, and agency operations managers.
* **Why It Matters:** As demonstrated in [*Invoice Haystack* (`arXiv:2606.25343`, June 2026)](http://arxiv.org/abs/2606.25343v3), standard vector RAG suffers from severe *embedding collapse* (0.73 mean pairwise cosine similarity) on visually homogeneous invoices, missing duplicate billings or altered IBAN/PayPal recipient emails ([HN #40595650](https://news.ycombinator.com/item?id=40595650)).
* **Current Workaround:** Staring at PDFs side-by-side with an Excel spreadsheet and PayPal transaction history, or paying \$20k+/yr for enterprise AP tools like Stampli or Vic.ai.
* **Technical Difficulty:** Medium
* **Hackathon Feasibility:** **High** (FastAPI + PDF parsing + hybrid Elastic/SQLite search + PayPal Invoicing & Transaction Search API + AG Grid).
* **Alignment with Official Directions & Prizes:**
  * *Directions:* Business Solutions (Primary), AI Agents or Automation.
  * *Prizes:* **Best Use of AG Grid (\$5,000)**, **Best Use of PayPal + AI (\$5,000)**.
* **Potential Demo Moment:** Drop a batch of 20 vendor PDF invoices into the app; the AI flags 1 subtle duplicate invoice (same line items, shifted invoice number) and 1 spoofed vendor email address, while auto-matching the 18 valid invoices to POs and queuing them for one-click PayPal settlement.

---

### Sub-Problem 8: AI-Generated Self-Serve Financial & Subscription Operations Dashboards ("Dashboard Without Building a Dashboard")
* **Problem Statement:** Small merchants and SaaS founders using PayPal Subscriptions, Orders, and Disputes cannot get answers to ad-hoc operational questions (e.g., *"Which customer segment has the highest refund spike this week, and which subscriptions failed renewal?"*) without exporting CSVs or hiring a developer to build custom BI views.
* **Who Experiences It:** Non-technical merchants, indie SaaS founders, and nonprofit directors running on PayPal.
* **Why It Matters:** Highlighted directly by PayPal's official Oct 12 hackathon webinar (*["Build a payments dashboard without building a dashboard"](https://www.youtube.com/watch?v=LGfG44i1Fj8)*) and the **AG Studio Agent Framework** track (\$10,000 prize pool across 5 winners).
* **Current Workaround:** Downloading monthly CSVs from `paypal.com/reports` and building pivot tables in Excel.
* **Technical Difficulty:** Easy–Medium
* **Hackathon Feasibility:** **High** (AG Studio + Studio Agent Framework + PayPal Agent Toolkit / Transaction Search & Subscriptions APIs).
* **Alignment with Official Directions & Prizes:**
  * *Directions:* Business Solutions, Money Movement Experiences.
  * *Prizes:* **Best Use of AG Grid (1st: \$5k, 2nd: \$2k, 3rd: 3x \$1k)**.
* **Potential Demo Moment:** Type a natural-language prompt (*"Show me a live refund-anomaly radar by product and a scoreboard of overdue invoices with one-click AI nudge buttons"*); the **AG Studio Agent Framework** dynamically constructs the multi-widget cross-filtering dashboard live on screen and triggers a PayPal invoice reminder directly from a grid row.
