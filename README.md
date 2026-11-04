# PayPal AI Hackathon 2026 — Research Dossier & Project Strategy

> **Challenge:** Build What's Next with PayPal and AI  
> **Host:** Devpost ([paypalaihackathon.devpost.com](https://paypalaihackathon.devpost.com/))  
> **Submission Deadline:** November 12, 2026 @ 12:00 PM PST  
> **Total Prize Pool:** \$69,750  
> **Repository Status:** Private Workspace & Research Hub

---

## 🎯 Executive Summary

This repository contains the end-to-end strategic research, technical benchmarking, user pain point validation, competitive intelligence, and implementation architecture for competing in the **PayPal AI Hackathon 2026**.

Our primary project proposal is **PactGuard AI** — an autonomous agentic procurement, multi-agent negotiation, and spend-mandate control plane for PayPal. It combines **Channel3** product discovery, **Constitutional Multi-Agent Negotiation** (governed by academic benchmarks), **4-Factor Auto-Purchase Mandate Firewalls** (`arXiv:2610.29216`), and atomic **PayPal Orders, Invoicing, and Payouts** settlement inside an **AG Studio** self-serve analytics command center.

---

## 📁 Repository Structure

The documentation is organized following industry standards for modularity and ease of consumption:

```text
paypal-ai-hackathon/
├── README.md                                  # Repository overview and quick start
└── docs/
    ├── 01-problem-decomposition.md            # 8 decomposed sub-problems, difficulty & feasibility
    ├── 02-literature-and-technical-landscape.md # 10 verified arXiv papers (2025-2026) & protocols
    ├── 03-user-pain-points-and-signals.md     # 12 verified user pain points (GitHub, HN, Reddit, SO)
    ├── 04-competitor-and-prior-art.md         # 14 direct/adjacent competitors & sponsor matrix
    ├── 05-feature-ideation.md                 # 25 concrete product concepts with full metadata
    ├── 06-idea-ranking.md                     # 8-criteria scoring matrix & ranking table
    ├── 07-top-3-recommendations.md            # Detailed briefs for PactGuard, AegisPay, ChronoPay
    ├── 08-final-recommendation-and-roadmap.md # Strategic choice, 36h sprint plan & demo script
    ├── 09-implementation-framework.md         # Unified full loop: stage→code map, guard matrix, readiness
    ├── 10-execution-plan.md                   # Phased delivery: pain points → solutions, per-phase technicalities
    ├── 11-dashboard-ui-plan.md                # Design system, screens, AG Studio reference, UI tasks per phase
    └── full-research-dossier.md               # Complete consolidated single-file dossier
```

---

## 🏆 Prize Optimization & Sponsor Alignment Strategy

According to **Section 8 of the Official Rules** (verified via the [Devpost FAQ](https://paypalaihackathon.devpost.com/details/faqs)):
> *"You can use more than one sponsor tool, and you'll be considered for the sponsor prize of each tool you use, but a single project can win at most one Sponsor Prize plus either one Grand Prize or one Honorable Mention Prize."*

By building **PactGuard AI**, we target the maximum allowable winning footprint across both overall and sponsor tracks:

| Award Track | Prize Value | Lead Judge on Panel | Integrated Capability |
| :--- | :--- | :--- | :--- |
| **1st Place Grand Prize** | **\$12,000 cash** | PayPal Developer Advocates & PMs | Complete, working end-to-end multi-agent financial system |
| **Best Use of Agentic Commerce** | **\$5,000 cash** | PayPal Engineering Leadership | Multi-agent autonomous discovery, negotiation, and settlement |
| **Best Use of PayPal + AI** | **\$5,000 cash** | PayPal Engineering Leadership | Deep use of `@paypal/agent-toolkit`, Orders v2, Invoices v2, Payouts |
| **Best Use of AG Grid (1st Place)** | **\$5,000 cash** | Sylwia Vargas (Sr. Tech Community Mgr, AG Grid) | Embedded AG Studio + Studio Agent Framework with custom widgets |
| **Best Use of Channel3** | **\$1,500 cash** | Ignacio Valdez Bicard (Founding Eng, Channel3) | Channel3 API / MCP for 100M+ real product graphs & pricing |
| **Best Use of APIMatic** | **\$1,000 cash** + 6mo Business | Ameer Hassan (Co-Founder, APIMatic) | APIMatic Context Plugin ensuring 0 API hallucinations & clean SDK |
| **Best Use of Render** | **\$1,000 credits** | Shifra Williams (Founding DevRel, Render) | Full-stack deployment + Render Workflows agent orchestration |

---

## 🛠️ Recommended Tech Stack

* **Backend:** Python 3.11+, FastAPI, Uvicorn, SQLite/PostgreSQL
* **Frontend:** React 18, TypeScript, Vite, Tailwind CSS
* **Fintech & Payment Rails:** `@paypal/agent-toolkit` (TypeScript/Python), PayPal Orders v2 REST API, PayPal Invoicing v2 REST API, PayPal Payouts API, PayPal Webhooks
* **AI & Agent Orchestration:** Anthropic Claude (`claude-opus-5-5`, optional — money decisions stay deterministic), Model Context Protocol (MCP), LangChain / custom async event loops
* **Sponsor Frameworks:** AG Studio (`@ag-grid-enterprise/all-modules` + Studio Agent Framework), Channel3 API/MCP, APIMatic Context Plugins
* **Deployment & Cloud:** Render (Web Service + Render Workflows)

---

## 🧩 Implementation (backend/)

The unified loop (**Delegate → Buy → Pay → Deliver → Pay out → Defend → Learn**) is implemented as ten stage modules sharing a hash-chained evidence ledger, a lineage ID, gate tokens and penny-exact money. See [`docs/09-implementation-framework.md`](docs/09-implementation-framework.md).

```bash
make setup
```

```bash
make test
```

```bash
make backend
```

`REPLAY_MODE=true` (the default) runs the whole demo arc offline; `POST /api/demo/run` returns the timeline.

### 🔬 Live Empirical Validation & Experiments
The codebase has been empirically verified against live sandbox APIs (documented in detail in [`docs/09-implementation-framework.md` §7](docs/09-implementation-framework.md#7-live-sandbox--integration-experiments-log-phases-0--1)):
* **Autonomous Vaulted-Wallet Execution (B-9):** Confirmed zero-popup server-side capture via PayPal Vault payment tokens (`vault_id: 8ng18757…`, Order `7LX28344P4713330H`, Capture `3L94707948760335B` `COMPLETED`).
* **Real-World Discovery & Pricing Baseline (Channel3):** Live catalog queries via `/v1/search` with header `x-api-key`, mapped through a verified retailer return-policy table (`RETURN_POLICY_DAYS`).
* **Spend Mandate Governance & Human Approval:** Deterministic 4-Factor Firewall (`Warrant`, `Reversibility`, `Price vs Baseline`, `Budget & Velocity`). Low-risk items under auto-threshold auto-settle; high-value negotiated items ($1,020 monitor batch) or items with hidden return terms require explicit user approval via the golden PayPal JS SDK button.
* **Cryptographic Ledger & Dispute Defense:** Tamper-evident SHA-256 hash chaining, dynamic ReportLab PDF evidence brief generation, and automated win probability calculation (95%). Tested against dispute fallback `PP-D-1001` (compensating for PayPal Sandbox UI Resolution Center server-side bugs).

---

## 🚀 Quick Navigation

* To review the technical and academic literature foundations, see [`docs/02-literature-and-technical-landscape.md`](docs/02-literature-and-technical-landscape.md).
* To understand real merchant and developer friction points in PayPal repos, see [`docs/03-user-pain-points-and-signals.md`](docs/03-user-pain-points-and-signals.md).
* For the full architecture, demo script, and evaluation plan of **PactGuard AI**, see [`docs/07-top-3-recommendations.md`](docs/07-top-3-recommendations.md) and [`docs/08-final-recommendation-and-roadmap.md`](docs/08-final-recommendation-and-roadmap.md).
* For the phased build plan (what is broken today, how we solve it, and the technical work in each phase), see [`docs/10-execution-plan.md`](docs/10-execution-plan.md).
* For UI and dashboard work (design tokens, Mission Control, the AG Studio Command Center, custom widgets, Studio agents, and the UI task tracker), see [`docs/11-dashboard-ui-plan.md`](docs/11-dashboard-ui-plan.md).
