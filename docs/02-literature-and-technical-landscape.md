# Section 2: Literature and Technical Landscape

This document summarizes the **10 most relevant, recent (2025–2026) academic research papers, technical reports, protocol standards, and open-source systems** directly informing our hackathon solution. Every paper and code repository cited below is verified and reproducible on consumer laptop compute.

---

### 1. *Preference Is Not Permission: Personalizing the Auto-Purchase Line in Agentic Commerce*
* **Title:** Preference Is Not Permission: Personalizing the Auto-Purchase Line in Agentic Commerce
* **Link:** [https://arxiv.org/abs/2610.29216v1](https://arxiv.org/abs/2610.29216v1)
* **Date:** October 21, 2026 (Authors: Ryotaro Shimizu, Sai HtaungKham, Mo Fan)
* **Core Contribution:** Formalizes the critical boundary between product *recommendation* and autonomous *financial commitment* ("the auto-purchase line"). Demonstrates across 16 instruction-tuned LLMs that models systematically **overreach**—committing user funds automatically even when product warrant/evidence is missing or reversibility (return policy) is low.
* **Methods / Models / Datasets:** Evaluates 16 instruction-tuned LLMs against a 15-annotator human authorization benchmark across four dimensions: **Warrant** (information sufficiency), **Reversibility** (refund/return policy), **Price Norm** (deviation from user baseline), and **Urgency**. Trains a lightweight shallow classifier on 30–40 user labels to predict the 3-valued decision (`DO_NOT_BUY`, `CONFIRM_FIRST`, `BUY_AUTOMATICALLY`), achieving 0.79 median accuracy and outperforming all 80 prompt×LLM configurations.
* **Limitations:** Learned boundaries are domain-specific and require initial calibration examples per user profile.
* **What We Can Reuse:** The exact **4-factor Auto-Purchase Gate (`Warrant`, `Reversibility`, `Price Norm`, `Urgency`)** outputting a 3-state routing decision (`Auto-Pay via PayPal`, `Request Human Approval`, `Reject`) can be implemented in `<150` lines of Python/scikit-learn on a laptop CPU!
* **Open Gap We Address:** Integrating this 3-valued commitment boundary directly as an MCP/Agent-Toolkit middleware wrapper around PayPal Orders and Channel3 product metadata.

---

### 2. *Provable Authority: A Protocol for Verifiable Authority Resolution and Control Across Human, Organizational, and Agentic Transactions*
* **Title:** Provable Authority: A Protocol for Verifiable Authority Resolution and Control Across Human, Organizational, and Agentic Transactions
* **Link:** [https://arxiv.org/abs/2610.22899v1](https://arxiv.org/abs/2610.22899v1)
* **Date:** October 16, 2026 (Authors: Jeremy Blackburn, Tim Hines, Matthew Koepp)
* **Core Contribution:** Introduces the **ChainIT Authority Protocol**, a pre-execution authority and evidence control plane for agentic payments. Separates identity from a versioned organizational authority record, binds human approvals and policy predicates to a **canonical transaction digest**, atomically reserves budget capacity under concurrency, and issues a single-use **Execution Authorization Credential (EAC)** consumed at the payment rail adapter.
* **Methods / Models / Datasets:** Cryptographic SHA-256 canonical transaction digests, deterministic reason-coded policy predicates, atomic budget reservation state machines, and append-only post-execution evidence sealing across fiat and digital rails.
* **Limitations:** Architectural protocol specification; does not ship a turnkey UI or PayPal MCP adapter out of the box.
* **What We Can Reuse:** Binding every PayPal Agent Toolkit mutation (`create_order`, `pay_order`, `send_invoice`, `create_payout`) to a **canonical transaction digest + single-use Execution Authorization Token** and an append-only audit log.
* **Open Gap We Address:** Building the first visual, developer-and-CFO-friendly implementation of pre-execution authority tokens and post-execution dispute evidence sealing on top of PayPal's Sandbox APIs.

---

### 3. *Get In, Decide, Prove: A Merchant-Side Readiness Benchmark for Agentic Commerce*
* **Title:** Get In, Decide, Prove: A Merchant-Side Readiness Benchmark for Agentic Commerce
* **Link:** [https://arxiv.org/abs/2610.17378v1](https://arxiv.org/abs/2610.17378v1)
* **Date:** October 12, 2026 (Authors: Adrian de Valois-Franklin, Alex Bogdan, Anas Ibrahim)
* **Core Contribution:** Evaluates 555 merchant websites named as clients of major payment processors on three questions: Can an AI agent *Get In* (access without bot blocks)? Can it *Decide* (are all-in total cost, return terms, service date, and variant identity machine-decidable)? Can it *Prove* (does the transaction leave admissible evidence for a payment dispute under the `RAILS` taxonomy)?
* **Methods / Models / Datasets:** Empirical census of 555 merchant sites across 3 browser profiles (declared bot, headless browser, user-present browser) and deterministic scoring of 330 merchants. Finds **18.9% (105 sites) block declared agents on the homepage**, and **only 18 of 330 merchants** expose a machine-decidable all-in total and refund policy without human intervention.
* **Limitations:** Pilot benchmark that measures merchant readiness rather than providing a remediation tool or checkout bridge.
* **What We Can Reuse:** Their **"Get In, Decide, Prove" readiness rubric** and **`RAILS` dispute-admissibility evidence snapshot** (capturing a timestamped hash of the merchant's stated price, SKU, and refund policy at the moment of purchase so neither buyer nor seller can lie during a subsequent PayPal SNAD dispute!).
* **Open Gap We Address:** Combining **Channel3** (or **KERNEL** cloud browser) + **PayPal** to capture a "Decide & Prove" evidence certificate at checkout that automatically attaches to PayPal transactions and defends against future disputes.

---

### 4. *Constitutional Gating and Deterministic Recovery for Multi-Agent LLM Negotiation*
* **Title:** Constitutional Gating and Deterministic Recovery for Multi-Agent LLM Negotiation: Ablations Against a Stateful Adversarial Gatekeeper
* **Link:** [https://arxiv.org/abs/2610.11542v3](https://arxiv.org/abs/2610.11542v3)
* **Date:** October 8, 2026 (Authors: Masaaki Nakatsu, Reno Wang)
* **Core Contribution:** Identifies the three primary failure modes of multi-agent LLM negotiations: (1) *"polite loops"* that never close a deal, (2) malformed schema outputs that break downstream APIs, and (3) compliance deadlocks against adversarial counterparts. Proposes a **5-Pillar Runtime Constitution**, a **Schema Hard Gate**, and **Cognitive Annealing** (deterministic deadlock detection + context reset), cutting token consumption by **67–73%** and escaping deadlocks **5/5 times** ($p = 0.008$) vs. 0/5 for unconstrained LLM steering.
* **Methods / Models / Datasets:** Multi-agent ablation study (30 runs using Gemini 2.5 Pro and Claude Haiku 4.5) with deterministic regex/schema pre-flight gates and bounded stop rules.
* **Limitations:** Tested on a synthetic stateful gatekeeper benchmark rather than live payment settlement APIs.
* **What We Can Reuse:** The **Schema Hard Gate + Deterministic Deadlock Recovery** pattern—essential for a 3-minute hackathon demo so our negotiating agents never hang, hallucinate invalid JSON, or exceed 4 turns before settling via PayPal.
* **Open Gap We Address:** Connecting their constitutional negotiation loop directly to real PayPal Order/Invoice creation upon deal lock.

---

### 5. *Parallelism or Concession? Concurrency-Aware Procurement Negotiation for Agentic Commerce*
* **Title:** Parallelism or Concession? Concurrency-Aware Procurement Negotiation for Agentic Commerce
* **Link:** [https://arxiv.org/abs/2610.06017v1](https://arxiv.org/abs/2610.06017v1)
* **Date:** October 5, 2026 (Authors: Xiaolin Xu, Donghao Zhu)
* **Core Contribution:** Proves mathematically and empirically that when an AI buyer agent negotiates concurrently with multiple sellers under a deadline, *parallelism substitutes for price concession* (running 3–5 concurrent seller threads allows a strictly lower reservation price cap), but creates **simultaneous commitment risk** (accidentally buying from two sellers at once) unless governed by a central coordinator (**CANO**: Concurrency-Aware Negotiation Optimizer).
* **Methods / Models / Datasets:** Quantile acceptance curves, Monte Carlo stress tests, and deterministic concurrency/price-cap optimization.
* **Limitations:** Assumes single-unit procurement and focuses on mathematical optimization rather than payment rail locking.
* **What We Can Reuse:** The **two-phase reservation-to-capture pattern** (negotiate concurrently with $N$ suppliers using soft quotes, then issue a single PayPal Order authorization/capture only to the winning supplier while auto-canceling runner-up threads).
* **Open Gap We Address:** Implementing a visual multi-supplier negotiation arena where users watch parallel agent threads bargain down prices and execute a single atomic PayPal settlement.

---

### 6. *Do LLM Agents Negotiate Rationally? A Mechanism-Design Framework for Verifiable Multi-Agent Interaction over A2A/MCP*
* **Title:** Do LLM Agents Negotiate Rationally? A Mechanism-Design Framework for Verifiable Multi-Agent Interaction over A2A/MCP
* **Link:** [https://arxiv.org/abs/2608.14613v1](https://arxiv.org/abs/2608.14613v1)
* **Date:** July 10, 2026 (Authors: Wael Albayaydh, Rui Zhao)
* **Core Contribution:** Shows that while Anthropic's **MCP** and Google's **A2A** standardize tool and agent transport, unstructured LLM dialogue fails game-theoretic rationality and fair-allocation invariants (achieving only 4.2% usable outcomes on 3-party allocation without verification). Introduces a **lightweight runtime verification and repair layer over MCP/A2A message schemas** encoding alternating-offers bargaining and Vickrey-Clarke-Groves (VCG) auctions, raising negotiation completion to **100%**.
* **Methods / Models / Datasets:** Alternating-offers bargaining and VCG auction constraints enforced over A2A/MCP JSON schemas ($N=30$ trials per condition).
* **Limitations:** Focuses on protocol verification rather than end-user UI or fiat settlement.
* **What We Can Reuse:** Structured **Alternating-Offers JSON state machines over MCP** (`PROPOSE`, `COUNTER`, `ACCEPT_WITH_DIGEST`, `REJECT`) with runtime invariant checks so multi-agent negotiations complete deterministically in 100% of demo runs.
* **Open Gap We Address:** Coupling verifiable A2A/MCP negotiation schemas with PayPal's MCP server tools.

---

### 7. *Securing Agentic Commerce Through Behavior-Aware Fraud Detection (ACAGS)*
* **Title:** Securing Agentic Commerce Through Behavior-Aware Fraud Detection and Cybersecurity for Trusted AI-Agent Payment Authorization
* **Link:** [https://arxiv.org/abs/2610.27483v1](https://arxiv.org/abs/2610.27483v1)
* **Date:** October 20, 2026 (Author: Kayode L. Ogunsusi)
* **Core Contribution:** Introduces the **Autonomous Commerce Agent Guard System (ACAGS)**, combining behavioral analytics, agent-specific authorization controls, and **SHAP explainable AI** (`APPROVE`, `REVIEW`, `REJECT`) to detect compromised agents, prompt-injected delegation abuse, and abnormal velocity. Achieves **99.77%** detection of abnormal agent behavior and **100%** detection of authorization-scope violations.
* **Methods / Models / Datasets:** XGBoost classifier + SHAP explainability trained on synthetic financial transaction data augmented with 5 adversarial agent scenarios.
* **Limitations:** Evaluated on synthetic transactions; requires integration into a live payment gateway.
* **What We Can Reuse:** A lightweight **XGBoost / rule-hybrid risk scorer with SHAP feature attribution bars** rendered in the UI for every agent payment request (`APPROVE` / `REVIEW` / `REJECT`).
* **Open Gap We Address:** Embedding explainable agent anomaly scoring directly inside an AG Grid / AG Studio real-time PayPal control center.

---

### 8. *MerchantBench & E-Commerce Bench (Long-Horizon Autonomous Commerce Benchmarks)*
* **Title:** *MerchantBench: Benchmarking LLM Agents for Long-Term Coherence in E-Commerce Operations* & *E-Commerce Bench: Evaluating LLM Agents on Long-Horizon Autonomous Business Operation*
* **Links:** [https://arxiv.org/abs/2607.28956v2](https://arxiv.org/abs/2607.28956v2) (July 31, 2026) and [https://arxiv.org/abs/2608.30730v1](https://arxiv.org/abs/2608.30730v1) / [GitHub: `QwenLM/E-CommerceBench`](https://github.com/QwenLM/E-CommerceBench) (August 31, 2026)
* **Core Contribution:** Evaluate frontier LLMs across 365 simulated days of seller-side e-commerce (98,843 real product records, 26 operational tools, supplier negotiation, cash-flow management, returns, and fraud avoidance). Reveal that **even top frontier LLMs achieve only 27.3% of human net assets** when left unassisted, and the highest-earning model (`GPT-5.6 Sol`) ranks **16th out of 18 on fraud avoidance** because it aggressively approves risky transactions.
* **Methods / Models / Datasets:** 98,843 e-commerce product records, 26 MCP-style operational tools, deterministic demand/negotiation kernels.
* **Limitations:** Pure simulation benchmarks without real payment sandbox execution.
* **What We Can Reuse:** Empirical proof for our hackathon pitch that **autonomous commerce agents require structured financial guardrails, cash-flow visibility, and fraud/dispute protection**, plus reusable product/supplier dataset schemas from `QwenLM/E-CommerceBench`.
* **Open Gap We Address:** Providing the operational copilot + human-in-the-loop control plane that bridges the gap between raw LLM agents and safe PayPal merchant execution.

---

### 9. *Invoice Haystack & Invoice Information Extraction (Docling + Hybrid VLM-RAG)*
* **Title:** *Invoice Haystack: Benchmarking Document Retrieval and Visual Question Answering Under Strong Visual Homogeneity* & *Invoice Information Extraction: Methods and Performance Evaluation*
* **Links:** [https://arxiv.org/abs/2606.25343v3](https://arxiv.org/abs/2606.25343v3) (June 24, 2026) and [https://arxiv.org/abs/2510.15727v2](https://arxiv.org/abs/2510.15727v2) (October 17, 2025)
* **Core Contribution:** *Invoice Haystack* demonstrates that standard vision-language embeddings collapse when indexing hundreds of visually similar invoices (mean cosine similarity 0.73), and proposes **VL-RAG** (hybrid text/BM25 + visual embeddings + VLM verification filter), boosting Recall@1 by +13.5 percentage points. *Invoice Information Extraction* benchmarks **Docling + LLM structured extraction** with automated arithmetic/consistency checks (verifying `sum(quantity * unit_price) + tax == total`).
* **Methods / Models / Datasets:** 1,500 anonymized invoice images + 200 discriminative QA pairs; IBM `Docling` open-source PDF parser; field-level precision and arithmetic consistency checks. Public datasets include **CORD** ([Consolidated Receipt Dataset on HuggingFace](https://huggingface.co/datasets/naver-clova-ix/cord-v2)), **SROIE**, and **FATURA**.
* **Limitations:** Standalone extraction pipelines; not wired into payment execution or PayPal Invoicing/Payouts APIs.
* **What We Can Reuse:** **Docling / Vision-LLM structured JSON extraction + deterministic arithmetic consistency verification** (catching PayPal's own [`create_order` tax-rounding bug documented in `paypal/agent-toolkit` PR #110](https://github.com/paypal/agent-toolkit/pull/110)!), plus **Elastic hybrid BM25 + vector search** to prevent embedding collapse across similar invoices.
* **Open Gap We Address:** End-to-end "PDF/Receipt In -> Verified Arithmetic & Duplicate Check -> PayPal Invoice / Payout Out."

---

### 10. *PayPal Agent Toolkit (`@paypal/agent-toolkit`) & Google/FIDO Agent Payments Protocol (AP2)*
* **Title:** PayPal Agent Toolkit & MCP Server + Google/FIDO Agent Payments Protocol (AP2)
* **Links:** [GitHub: `paypal/agent-toolkit`](https://github.com/paypal/agent-toolkit), [PayPal AI Docs](https://docs.paypal.ai/), [AP2 Specification Blog](https://blog.google/technology/ai/)
* **Date:** Active 2025–October 2026 (Latest PRs #107–#118 in Oct 2026)
* **Core Contribution:** `paypal/agent-toolkit` provides official TypeScript and Python wrappers and an MCP server exposing **46 tools** across PayPal **Invoices** (`create_invoice`, `send_invoice`, `generate_invoice_qr_code`, recurring series), **Orders** (`create_order`, `get_order_details`, `pay_order`), **Disputes** (`list_disputes`, `get_dispute`, `accept_dispute_claim`), **Shipment Tracking**, **Catalog Products**, **Subscriptions**, and **Transactions Search**. AP2 defines cryptographically signed **Intent Mandates** and **Cart Mandates** for delegated agent spending.
* **Limitations (Verified via Oct 2026 GitHub Issues):**
  1. Missing Payouts tools in stable release ([PR #107](https://github.com/paypal/agent-toolkit/pull/107) opened Oct 4, 2026).
  2. Missing Dispute Evidence Submission (`provide-evidence` / counter-claim) — the toolkit only exposes `list_disputes`, `get_dispute`, and `accept_dispute_claim` (surrendering the dispute!), leaving merchants unable to *fight* a dispute via the agent toolkit!
  3. No built-in spend policy gate, human approval hook, or MCP `destructiveHint` annotations ([Issues #95](https://github.com/paypal/agent-toolkit/issues/95), [#105](https://github.com/paypal/agent-toolkit/issues/105), [#114](https://github.com/paypal/agent-toolkit/issues/114)).
* **What We Can Reuse:** The official `paypal-agent-toolkit` / `@paypal/agent-toolkit` as our foundation, extended with custom tools generated/validated via **APIMatic Context Plugins for PayPal** for the missing **Disputes Evidence Submission** and **Payouts** endpoints!
