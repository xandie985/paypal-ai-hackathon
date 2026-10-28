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
* **AI & Agent Orchestration:** OpenAI API (`gpt-4o`, `gpt-4o-mini`) / Anthropic Claude (`claude-3-5-sonnet`), Model Context Protocol (MCP), LangChain / custom async event loops
* **Sponsor Frameworks:** AG Studio (`@ag-grid-enterprise/all-modules` + Studio Agent Framework), Channel3 API/MCP, APIMatic Context Plugins
* **Deployment & Cloud:** Render (Web Service + Render Workflows)

---

## 🚀 Quick Navigation

* To review the technical and academic literature foundations, see [`docs/02-literature-and-technical-landscape.md`](docs/02-literature-and-technical-landscape.md).
* To understand real merchant and developer friction points in PayPal repos, see [`docs/03-user-pain-points-and-signals.md`](docs/03-user-pain-points-and-signals.md).
* For the full architecture, demo script, and evaluation plan of **PactGuard AI**, see [`docs/07-top-3-recommendations.md`](docs/07-top-3-recommendations.md) and [`docs/08-final-recommendation-and-roadmap.md`](docs/08-final-recommendation-and-roadmap.md).
