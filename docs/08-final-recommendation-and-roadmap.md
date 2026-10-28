# Section 8: Final Recommendation & Implementation Roadmap

This document establishes the **single best project choice** for the hackathon team, explains why it offers the highest probability of winning, and lays out the exact **36-hour sprint plan**, MVP scope boundaries, and pitch narrative.

---

## 🎯 The Strategic Choice: **PactGuard AI**

### Why It Is the Best Fit for Your Team
1. **Unmatched Prize Surface Area:**
   * **Overall & Category Prizes:** Laser-targeted at **1st Place Grand Prize (\$12,000)**, **Best Use of Agentic Commerce (\$5,000)**, and **Best Use of PayPal + AI (\$5,000)**.
   * **Sponsor Prize Stacking (Section 8 Rules Compliance):** Qualifies simultaneously for **AG Grid (\$5,000 1st Place)** via AG Studio, **Channel3 (\$1,500)** via live product data, **APIMatic (\$1,000 x3)** via validated SDK generation, and **Render (\$1,000 credits)** via live deployment.
2. **Direct Alignment with Hackathon Headline:**
   * Directly solves PayPal's core challenge: *"What happens when you put AI behind the wheel... an AI agent that shops and checks out for you... or two agents negotiating and settling a payment between themselves (agent-to-agent commerce)."*
3. **Feasible on Standard Compute:**
   * Requires no dedicated GPU cluster. Uses fast cloud LLMs (`gpt-4o-mini`, `claude-3-5-haiku`) alongside lightweight Python scikit-learn logic on laptop CPUs.

---

## 📅 36-Hour Sprint Execution Plan

```text
[Hours 01-06: Foundation & Connectivity]
 ├── Setup monorepo: FastAPI backend + React/Vite/Tailwind frontend on Render
 ├── Verify PayPal Sandbox authentication (Client ID & Secret)
 ├── Ingest APIMatic Context Plugin for PayPal OpenAPI schemas
 └── Connect Channel3 API (using PAYPAL-HACKATHON-2026 promo key)

[Hours 07-14: Core Agent Engines]
 ├── Implement 3-Supplier Parallel Negotiation Engine (asyncio.gather, 3 turns max)
 ├── Implement 4-Factor Auto-Purchase Mandate Firewall (Warrant, Reversibility, Price, Budget)
 └── Inject per-call SHA-256 PayPal-Request-Id idempotency & tax reconciliation

[Hours 15-24: Frontend & Sponsor Integration]
 ├── Build React Sourcing UI & Live 3-Supplier Negotiation Arena
 ├── Build Mandate Firewall Drawer (Auto-Settle, Approval Card, Blocked Card)
 ├── Integrate PayPal JS SDK v6 buttons for 1-click human approval
 └── Embed AG Studio & Studio Agent Framework with 3 custom FinOps widgets

[Hours 25-30: Differentiation & Edge-Case Polish]
 ├── Add "Decide & Prove" Terms Certificate PDF generator (dispute immunity)
 ├── Add "Simulate Prompt-Injection Attack" red-team button
 └── Deploy live instance on Render (using Render Workflows for agent tasks)

[Hours 31-36: Verification, Documentation & Video Production]
 ├── Run end-to-end sandbox tests (verifying real PayPal Order IDs)
 ├── Write production-grade README.md with architecture & run commands
 └── Record & edit the <3:00 YouTube presentation demo video
```

---

## 🚫 What to Avoid Overbuilding

* **Do NOT build user authentication / multi-tenancy:** Start the demo directly in an authenticated, pre-seeded executive dashboard.
* **Do NOT rely on live web scraping:** Use the official **Channel3 API** for real 100M+ product normalization in `<200ms` without bot blocks.
* **Do NOT allow unbounded agent conversations:** Enforce a strict **3-turn negotiation protocol** (`Initial Quote` -> `Counter with Comp` -> `Best & Final Lock`) so negotiations complete smoothly in under 4 seconds during the video.

---

## 🎤 The Winning 3-Minute Demo Pitch Script

* **[0:00–0:25] The Hook & Verified Pain:**  
  *"PayPal moves money for 400 million accounts—and now AI agents are stepping behind the wheel. But when we audited PayPal's official `agent-toolkit` and recent 2026 research, we found three critical roadblocks stopping businesses from trusting AI with their wallet: agents can't reliably extract product terms across the web, they over-concede in supplier negotiations, and they have zero built-in spend gates or idempotency before firing `pay_order`. That's why we built **PactGuard AI**: the autonomous procurement, negotiation, and spend-mandate control plane for PayPal."*

* **[0:25–1:05] Channel3 Discovery + Parallel Agent Negotiation:**  
  *"Watch what happens when we ask PactGuard to equip a 5-person engineering team under \$1,500. First, it queries **Channel3's** 100-million product graph for verified retail baselines and return policies. Next, our Constitutional Negotiation Engine bargains in parallel with three wholesale supplier agents—driving the bundle price down by 18% in three deterministic rounds, locked with a cryptographic commitment hash."*

* **[1:05–2:00] The 4-Factor Mandate Firewall & Live PayPal Settlement:**  
  *"Before a single dollar moves, every transaction hits our **4-Factor Auto-Purchase Firewall**. Low-risk, reversible items under \$200 auto-settle instantly via **PayPal Orders v2** with cryptographic per-call idempotency. High-value negotiated contracts pause for a 1-click human approval right on screen, generating a real **PayPal Invoice and Order** plus a sealed 'Decide & Prove' terms certificate that makes future chargebacks effortless to win. And when a simulated prompt-injection attack tries to trigger an unauthorized payout, PactGuard blocks it in 8 milliseconds."*

* **[2:00–2:40] AG Studio "Dashboard Without a Dashboard":**  
  *"Finally, inside our embedded **AG Studio** command center, our finance team can query savings, audit trails, and risk telemetry in plain English. Watch AG Studio build live cross-filtering charts and audit grids on the fly."*

* **[2:40–3:00] Summary & Sponsor Close:**  
  *"Built with **PayPal Agent Toolkit**, **Channel3**, **AG Studio**, **APIMatic**, and **Render**, PactGuard AI turns raw LLMs into rational, governed economic actors on PayPal."*
