# 🛰️ Skylark BI Agent

A conversational **business-intelligence agent** that answers founder-level
questions over messy **monday.com** data — a sales **Deals** pipeline and
**Work Orders** execution/finance board — in plain English, with **auditable
numbers** and honest **data-quality caveats**.

> Built for the Skylark Drones Full-Stack Developer assignment.

- **Live app:** https://skylark-bi-agent-jylb.onrender.com
- **Repo:** https://github.com/niranjanagopinath/Skylark-Drones-Agent

> ⏳ **First load may take ~30–50s** — the free Render tier sleeps after idle and
> cold-starts on the next request. Subsequent requests are fast. Refresh once if
> the first hit is slow.

It's a calm, enterprise-style **BI workspace** — an Overview dashboard plus focused
Sales, Operations and Financials views — with an **Ask** page for natural-language
analysis. Every answer carries its data-quality caveats and a "How this was
calculated" panel. Ask things like *"Which sectors have the strongest pipeline?"*,
*"What's our win rate in mining?"*, or *"Give me a leadership update."*

---

## Table of contents
1. [What it does](#what-it-does) 
2. [Architecture](#architecture)
3. [The core principle: AI vs arithmetic](#core-principle)
4. [Data flow](#data-flow) 
5. [Data-quality strategy](#data-quality)
6. [Business logic](#business-logic) 
7. [monday.com integration](#monday)
8. [Setup](#setup)
9. [Testing](#testing)
10. [Deployment](#deployment)
11. [Assumptions & trade-offs](#assumptions)
12. [Limitations & future work](#limitations)
13. [AI tools & challenges](#ai-tools)

---

<a name="what-it-does"></a>
## 1. What it does
- Understands a natural-language business question and maps it to a **metric +
  filters** (sector, timeframe).
- Computes the answer **deterministically** from live monday data.
- **Narrates** it for a founder, and attaches the **caveats** and an
  **"how this was computed"** audit trail so the figure can be trusted/verified.
- Asks for **clarification** when a question is ambiguous or unsupported — it
  never guesses a number.

Supported metrics: pipeline health, revenue & collections, win rate, sector
performance (cross-board), deal status/stage breakdowns, receivables, a composite
**leadership update**, and a **data-quality** report.

---

<a name="architecture"></a>
## 2. Architecture

```
                         ┌─────────────────────────────────────────────┐
   Browser (chat UI) ───▶│  FastAPI  (one deployable unit)             │
   /static + /api        │                                             │
                         │   agent.py  ── orchestration                │
                         │      │                                      │
                         │      ├─▶ intent.py    ─▶ LLM Provider       │  ← interpret
                         │      │   (structured tool-call | keyword)   │
                         │      │                                      │
                         │      ├─▶ datasource.py ─▶ monday_client.py ─┼─▶ monday.com
                         │      │   (cache + normalize)                │   GraphQL (read-only)
                         │      │        │                             │
                         │      │        └─▶ normalize.py (clean + DQ) │
                         │      │                                      │
                         │      ├─▶ bi_engine.py  ── DETERMINISTIC     │  ← compute (no LLM)
                         │      │                                      │
                         │      └─▶ narrate.py    ─▶ LLM Provider      │  ← explain
                         └─────────────────────────────────────────────┘

  One-time setup:  Excel ──▶ scripts/ingest_to_monday.py ──▶ monday boards
                                                          └─▶ board_config.json
```

**Modules**
| File | Responsibility |
|---|---|
| `scripts/ingest_to_monday.py` | One-time ETL: Excel → two monday boards (+ `board_config.json`). |
| `app/monday_client.py` | Read-only monday GraphQL client (paginates all items). |
| `app/normalize.py` | Cleaning + `DataQualityReport` (dedup, coverage, negatives). |
| `app/datasource.py` | Maps monday column-ids → logical fields; TTL cache; stale-fallback. |
| `app/bi_engine.py` | **All numeric computation.** Each metric returns value + caveats + audit. |
| `app/intent.py` | NL → structured `Intent` (LLM tool-call, deterministic fallback). |
| `app/timeframe.py` | "this quarter" → concrete date range. |
| `app/narrate.py` | Result → founder-readable prose (LLM, template fallback). |
| `app/agent.py` | Pipeline glue + clarification/error handling. |
| `app/main.py` | FastAPI API + static frontend (adds a composed `/api/dashboard`). |
| `frontend/` | Vanilla-JS **BI workspace** — Overview / Sales / Operations / Financials / **Ask** — with a methodology-first audit panel. |

---

<a name="core-principle"></a>
## 3. The core principle: AI vs arithmetic
There is a **hard wall** between AI reasoning and business calculation:

- **The LLM interprets and explains.** It turns English into a structured intent
  and narrates the finished result.
- **Python computes every number** in `bi_engine.py`, and those calculations are
  **unit-tested against hand-verified fixtures**.

Why: an LLM that "reads the spreadsheet and answers" produces numbers no one can
verify. By contrast, here *the number shown to the user can be independently
reproduced by a test* — the property a business actually needs. If the LLM (or its
API key) is unavailable, the agent still answers via a deterministic keyword parser
and template narration.

The LLM sits behind a **provider abstraction** (`app/llm.py`) supporting a free
deterministic mode (`none`), Groq's free tier (`groq`), and Anthropic (`anthropic`).
Because arithmetic is provider-independent, swapping or removing the LLM changes the
*phrasing*, never the *numbers*.


---

<a name="data-flow"></a>
## 4. Data flow
1. `POST /api/chat {question}` → `agent.answer()`.
2. `intent.parse_intent()` → `{metric, sector, timeframe}` (or a clarification).
3. `datasource.get_dataset()` → fetch both boards (cached), map to logical fields,
   `normalize()` → clean DataFrames + `DataQualityReport`.
4. `bi_engine.METRICS[metric](...)` → `MetricResult{summary_values, caveats, audit}`.
5. `narrate.narrate()` → prose using **only** the computed numbers.
6. Response includes the answer, caveats, assumptions, the audit trail, and the
   data-source freshness.

---

<a name="data-quality"></a>
## 5. Data-quality strategy
The data is genuinely messy; the strategy is to **normalize safely, preserve the
rest, and always disclose**:

| Issue (found in data) | Handling |
|---|---|
| Stray "header echo" rows (`Sector/service`, `Deal Stage`…) | Dropped at ingestion; re-filtered at query time. |
| 12 exact-duplicate deals | Removed only on **full business-field match**; count reported. |
| Deal Value ~48% populated; Collected ~44% | Kept as `NaN` (never 0); metrics report coverage %. |
| Negative billed/collected amounts | Preserved (credit notes) but **counted & flagged**. |
| Excel date serials (e.g. `46079`) | Converted to ISO dates. |
| Inconsistent categories | Whitespace/case fixed; **distinct real categories never merged**. |
| Sectors in one board but not the other | Shown as zero on the missing side (real coverage, not an error). |
| Unknown sector asked for (e.g. "healthcare") | Returns 0 with a caveat listing the sectors that *do* exist — never mislabels all-company data. |

Every metric surfaces the caveats relevant to *that* figure. See
`GET /api/quality` and the **Data quality** panel in the UI.

---

<a name="business-logic"></a>
## 6. Business logic (definitions)
- **Open pipeline** = deals not `Won`/`Dead`; **open value** = Σ Deal Value over those.
- **Weighted pipeline** = Σ (Deal Value × factor), factors `High .8 / Med .5 / Low .2`
  (assumption, disclosed) over open deals having *both* value and probability.
- **Win rate** = `Won / (Won + Dead)`.
- **Billing efficiency** = `Σ billed / Σ order value`; **Collection efficiency**
  = `Σ collected / Σ billed`.
- **Leadership update** = pipeline + revenue + top sectors + the caveats to know.

Definitions live in code with an `audit` block per result, and in
[`DECISION_LOG.md`](./DECISION_LOG.md).

---

<a name="monday"></a>
## 7. monday.com integration
- **Read-only at runtime** via the GraphQL API (`items_page` pagination). The app
  reads board/column ids from `board_config.json` — monday's opaque ids are never
  hardcoded in logic.
- **One-time import:** `scripts/ingest_to_monday.py` reads the two Excel files and
  creates the boards. I re-ran the import because the pre-existing boards had all
  numeric columns empty (see Decision Log #2); the script preserves messiness and
  is the reproducible "monday setup".
- Data is **not** hardcoded — remove the boards and the app correctly reports the
  data source is unavailable.

---

<a name="setup"></a>
## 8. Setup (local)
```bash
# 1. Install
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# 2. Configure secrets
cp backend/.env.example backend/.env
#   set MONDAY_API_TOKEN (required) and ANTHROPIC_API_KEY (optional)

# 3. One-time: create + populate the monday boards
python scripts/ingest_to_monday.py       # writes backend/app/board_config.json

# 4. Run
cd backend && uvicorn app.main:app --reload --port 8000
# open http://localhost:8000
```

### Environment variables
| Var | Required | Purpose |
|---|---|---|
| `MONDAY_API_TOKEN` | ✅ | Read monday boards (+ write once for ingestion). |
| `LLM_PROVIDER` | — | `none` (default, free), `groq` (free tier), or `anthropic` (paid). |
| `GROQ_API_KEY` | — | Only if `LLM_PROVIDER=groq` — free key from console.groq.com. |
| `ANTHROPIC_API_KEY` | — | Only if `LLM_PROVIDER=anthropic` (requires paid credits). |
| `CACHE_TTL_SECONDS` | — | monday cache TTL (default 300). |

> **Cost:** the app defaults to `LLM_PROVIDER=none` (deterministic), so the hosted
> demo is **never a paid dependency** — anyone testing it cannot trigger billing.
> Set `LLM_PROVIDER=groq` with a free Groq key for richer natural-language
> understanding at **$0**. The LLM is abstracted behind `app/llm.py`, so switching
> providers is a one-line env change.

Secrets are read from env / `backend/.env` (git-ignored). No credentials in the
frontend or in git.

---

<a name="testing"></a>
## 9. Testing
```bash
cd backend && python -m pytest -q
```
31 tests cover normalization (dedup, header-echo, missing≠0, negatives, coverage,
date parsing), the BI engine (each metric hand-verified, sector filters, efficiency
ratios), intent + timeframe parsing, and the end-to-end agent (clarification,
graceful failure, disclosed assumptions). **Deterministic BI tests are isolated
from the LLM** — they need no API key and prove the numbers.

---

<a name="deployment"></a>
## 10. Deployment (Render)
Single Docker image (FastAPI serves API + frontend).
1. Push to GitHub → Render **New + → Blueprint** → select this repo (`render.yaml`).
2. Set `MONDAY_API_TOKEN` and `ANTHROPIC_API_KEY` (marked `sync:false`).
3. Deploy; health check at `/health`.

`board_config.json` is committed so the deployed app knows the board ids.

---

<a name="assumptions"></a>
## 11. Assumptions & trade-offs
See [`DECISION_LOG.md`](./DECISION_LOG.md) for the full list. Highlights: AI/arithmetic
wall; re-ingest to fix empty numeric columns; missing≠0; conservative dedup;
energy→Renewables (disclosed); single deployable unit; deterministic fallbacks.

---

<a name="limitations"></a>
## 12. Known limitations & future work
- Deals and Work Orders are aggregated **per sector independently**, not joined on a
  shared deal key (names are duplicated, so a reliable join needs more care).
- No receivables **aging** — invoice/collection dates are too sparse to trust.
- Single-turn (no conversational memory yet).
- Free-tier Render has cold starts (~30s first hit).

---

<a name="ai-tools"></a>
## 13. AI tools used & challenges
**AI tools:** Claude Code (Anthropic) assisted with scaffolding, implementation,
tests, and docs during development. At **runtime** the natural-language layer runs
through a provider abstraction that defaults to a free path (deterministic, or
Groq's free tier) so the hosted app carries no paid dependency. The architecture,
business definitions, data-quality strategy, and acceptance of results are my
engineering decisions (see Decision Log).

**Challenges:** (1) the pre-existing monday boards had empty numeric columns —
diagnosed via the API and fixed with a documented re-ingest; (2) real column drift
and header-echo rows in the source Excel; (3) keeping business numbers trustworthy
while still using AI — solved with the AI/arithmetic wall and independent tests.
