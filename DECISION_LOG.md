# Decision Log

Genuine decisions taken while building the Skylark BI Agent, with the reasoning
and the alternatives I rejected. (Kept to the ~2-page brief.)

## Key assumptions
- **Sector "energy" → "Renewables".** The data has no `Energy` sector; renewables
  (solar/wind) is its closest real proxy. The agent applies this alias *only to
  interpret questions* and **discloses it** in the answer. It never rewrites data.
- **Probability-weighted pipeline** uses assumed factors `High=0.8, Medium=0.5,
  Low=0.2` (data only gives High/Med/Low, not numbers). Shown as an explicit caveat.
- **"Open pipeline"** = deals whose status is neither `Won` nor `Dead`.
  **Win rate** = `Won / (Won + Dead)` (Open/On-Hold excluded from the denominator).
- **Revenue figures** come from Work Orders (execution/finance), **pipeline** from
  Deals. GST-inclusive amounts are used for billed/collected/receivable totals.
- **"This year"** = calendar YTD; **"FY"** = Indian financial year (Apr–Mar). The
  chosen interpretation is surfaced to the user.

## Decisions & trade-offs
1. **Hard wall: AI interprets, Python computes.** The LLM only (a) classifies the
   question into a structured intent and (b) narrates the finished result. *Every
   number is computed deterministically in `bi_engine.py` and unit-tested.*
   Rejected "let the LLM read rows and answer" — it's unverifiable and unsafe for
   business figures. Pay-off: any number the agent shows is reproducible by a test.
2. **Re-ingested the boards from Excel (`scripts/ingest_to_monday.py`).** I found
   the pre-existing monday boards had **100% empty numeric columns** (Deal Value and
   all Work-Order financials failed to import), which made revenue/pipeline metrics
   impossible. I wrote a documented, idempotent ETL that reloads all columns while
   **preserving** real messiness. This is the import the assignment asks for — the
   app still queries monday dynamically; nothing is hardcoded. Rejected patching the
   existing items (no stable key — names are duplicated cartoon characters).
3. **Missing ≠ zero.** Blank numbers become `NaN`, never 0, so sums/averages keep
   their meaning. Metrics report the coverage % behind each figure.
4. **Duplicates removed only on exact business-field match** (12 in Deals), and the
   count is always reported. Conservative: deals differing in any field are kept.
5. **"Header echo" rows dropped.** Spreadsheet artifacts where a header row leaked
   into the data (`Sector/service`, `Deal Stage`…) are not business records; they're
   removed at ingestion and defensively re-filtered at query time.
6. **Negative amounts preserved** (real credit notes / over-collection) but counted
   and flagged, rather than silently clipped to 0.
7. **Single deployable unit** (FastAPI serves the API *and* the static frontend).
   Trade-off: less horizontally scalable than split FE/BE, but far fewer moving
   parts, no CORS, one URL to keep alive — the right call for a 5-hour prototype.
8. **Deterministic fallback everywhere.** No LLM key or an LLM/monday outage → the
   agent still works via a keyword intent parser, template narration, and a stale
   cache. The system never fabricates an answer when a dependency fails; it says so.
9. **No paid runtime dependency; LLM behind a provider abstraction.** I verified
   the Anthropic key returns *"credit balance too low"* — i.e. it would be a paid
   dependency, and a recruiter testing the hosted app could incur cost. So the LLM
   is abstracted behind `app/llm.py` (`none` | `groq` | `anthropic`) and the app
   **defaults to `none`** (deterministic, free). Groq's free tier (no credit card)
   is the drop-in LLM for richer phrasing at $0. Because arithmetic is provider-
   independent, this choice never affects a number — only wording. Rejected making
   Anthropic a hard dependency.
10. **Tech stack:** Python/FastAPI/pandas (best-in-class for messy tabular BI +
   fast to write + trivial Docker deploy); provider-agnostic LLM; vanilla-JS
   frontend (no build step, instant deploy).

## How I interpreted "help prepare data for leadership updates"
A composite **Leadership Update** metric that assembles the numbers a founder would
put in a board update — pipeline (open + weighted value, win/loss), revenue
(billed, collected, receivable, billing/collection efficiency), and the top sectors
by billing — **plus the data-quality caveats they must know before quoting a
figure** (e.g. "Deal Value is only ~48% populated"). The differentiator is honesty:
it packages the caveats *with* the numbers so leadership isn't misled.

## What I'd do with more time
- Reconcile Deals ↔ Work Orders on a shared key (deal name/serial) for true
  deal-to-cash tracing, instead of aggregating per sector independently.
- Real receivables **aging** (needs reliable invoice/collection dates — currently
  too sparse/messy to trust).
- Multi-turn memory + follow-up context ("...and in railways?").
- Golden-answer regression tests that snapshot the full agent response.
- A background refresh + webhook so the cache is never stale.

## AI tools used
Claude Code (Anthropic) assisted with scaffolding, implementation, tests, and
docs. **The architecture, the AI/arithmetic boundary, the business definitions,
the data-quality strategy, prioritization, and the acceptance of every result are
engineering decisions I reviewed and own.**
