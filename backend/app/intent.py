"""
Query understanding.

Converts a founder's natural-language question into a validated `Intent`
(which metric to run, with which sector/timeframe filters). Two paths:

  * LLM path (Anthropic, structured tool-call) — robust to phrasing.
  * Deterministic keyword path — the always-available fallback, so the agent
    still works with no LLM key or during an LLM outage.

Crucially, the intent NEVER contains a computed number. It only names *what* to
compute; the deterministic BI engine does the computing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date

from . import schema
from .bi_engine import METRICS
from .config import settings
from .timeframe import resolve as resolve_timeframe

SUPPORTED_METRICS = list(METRICS.keys())


@dataclass
class Intent:
    metric: str                       # one of SUPPORTED_METRICS or "unsupported"
    sector: str | None = None
    timeframe: dict | None = None     # {"start","end","label"}
    needs_clarification: bool = False
    clarification: str | None = None
    assumptions: list[str] = field(default_factory=list)
    source: str = "rule-based"        # "llm" | "rule-based"
    raw_question: str = ""

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "sector": self.sector,
            "timeframe": self.timeframe,
            "needs_clarification": self.needs_clarification,
            "clarification": self.clarification,
            "assumptions": self.assumptions,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# Deterministic keyword parser
# ---------------------------------------------------------------------------
_METRIC_KEYWORDS = [
    ("leadership_update", ["leadership", "executive", "board update", "exec summary",
                           "leadership update", "prepare a summary", "briefing"]),
    ("data_quality", ["data quality", "coverage", "how complete", "missing data",
                      "completeness", "data issues"]),
    ("collections_summary", ["collection", "collect", "receivable", "outstanding",
                             "ar ", "overdue", "unpaid"]),
    ("revenue_summary", ["revenue", "billed", "billing", "invoice", "order value",
                         "sales value", "how much did we bill", "income"]),
    ("win_rate", ["win rate", "conversion rate", "close rate", "how many did we win",
                  "won vs lost"]),
    ("stage_breakdown", ["stage", "funnel breakdown", "by stage", "funnel stage"]),
    ("deal_status_breakdown", ["deal status", "by status", "status breakdown",
                               "open vs", "how many open"]),
    ("sector_performance", ["sector performance", "across sectors", "by sector",
                            "compare sectors", "which sector", "sector wise",
                            "sectoral"]),
    ("pipeline_health", ["pipeline", "funnel", "deals looking", "how's our pipeline",
                         "opportunities", "deal value"]),
]

_TIMEFRAME_PHRASES = [
    "this quarter", "current quarter", "last quarter", "previous quarter",
    "this month", "current month", "last month", "previous month",
    "this financial year", "financial year", "this fy", "fy",
    "this year", "current year", "ytd", "year to date",
]


def _extract_sector(text: str) -> tuple[str | None, list[str]]:
    t = text.lower()
    assumptions: list[str] = []
    for alias, canonical in schema.SECTOR_QUERY_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", t):
            if alias != canonical.lower():
                assumptions.append(
                    f"Interpreted '{alias}' as the '{canonical}' sector "
                    f"(the dataset has no explicit '{alias}' sector)."
                )
            return canonical, assumptions
    return None, assumptions


def _extract_timeframe(text: str, today: date | None = None) -> dict | None:
    t = text.lower()
    for phrase in _TIMEFRAME_PHRASES:
        if phrase in t:
            return resolve_timeframe(phrase, today)
    m = re.search(r"\b(20\d{2})\b", t)
    if m:
        return resolve_timeframe(m.group(1), today)
    return None


def parse_rule_based(question: str, today: date | None = None) -> Intent:
    t = question.lower().strip()
    sector, assumptions = _extract_sector(question)
    timeframe = _extract_timeframe(question, today)

    metric = None
    for name, keywords in _METRIC_KEYWORDS:
        if any(k in t for k in keywords):
            metric = name
            break

    # Sector mentioned but no explicit metric -> most useful default is a
    # pipeline read for that sector (matches the assignment's example query).
    if metric is None and sector:
        metric = "pipeline_health"

    if metric is None:
        return Intent(
            metric="unsupported",
            needs_clarification=True,
            clarification=(
                "I can answer questions about pipeline health, revenue & "
                "collections, win rate, and sector performance. Could you rephrase "
                "your question around one of those?"
            ),
            assumptions=assumptions,
            source="rule-based",
            raw_question=question,
        )

    return Intent(
        metric=metric, sector=sector, timeframe=timeframe,
        assumptions=assumptions, source="rule-based", raw_question=question,
    )


# ---------------------------------------------------------------------------
# LLM parser (provider-agnostic JSON output — works across Groq / Anthropic)
# ---------------------------------------------------------------------------
_SYSTEM = (
    "You classify founder-level business-intelligence questions for a company "
    "with two data sources: a sales Deals pipeline and Work Orders (execution + "
    "finance). Choose the single best metric. Do NOT compute or invent any "
    "numbers — only classify.\n\n"
    "Return ONLY a JSON object with these keys:\n"
    f"  metric: one of {SUPPORTED_METRICS + ['unsupported']}\n"
    "  sector: a sector name to filter by, or null. Map 'energy' to 'Renewables'. "
    f"Known sectors: {', '.join(schema.KNOWN_SECTORS)}. If the user names a "
    "sector-like term that is NOT in this list (e.g. 'healthcare'), put that term "
    "verbatim in sector (do NOT null it) so the system can report it is unknown.\n"
    "  timeframe_phrase: a relative timeframe if present (e.g. 'this quarter', "
    "'last month', 'FY', '2026'), else null.\n"
    "  needs_clarification: boolean (true if ambiguous or unsupported)\n"
    "  clarification: a short follow-up question if needed, else null.\n"
    "If the question cannot be answered from deals/work-orders data, set "
    "metric='unsupported' and needs_clarification=true."
)


def parse_llm(question: str, today: date | None = None) -> Intent:
    from .llm import get_provider

    raw = get_provider().complete(_SYSTEM, question, max_tokens=300, json_mode=True)
    # Be tolerant of models that wrap JSON in prose/code fences.
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"LLM did not return JSON: {raw[:120]}")
    data = json.loads(raw[start:end + 1])

    metric = data.get("metric", "unsupported")
    if metric not in SUPPORTED_METRICS and metric != "unsupported":
        metric = "unsupported"

    # Reuse deterministic sector/timeframe resolution for safety + assumptions.
    sector, assumptions = _extract_sector(question)
    if data.get("sector"):
        sector = data["sector"]
    timeframe = resolve_timeframe(data.get("timeframe_phrase"), today) \
        or _extract_timeframe(question, today)

    return Intent(
        metric=metric,
        sector=sector,
        timeframe=timeframe,
        needs_clarification=bool(data.get("needs_clarification")) or metric == "unsupported",
        clarification=data.get("clarification"),
        assumptions=assumptions,
        source="llm",
        raw_question=question,
    )


def _canonicalize_sector(intent: Intent) -> Intent:
    """Match the user's sector to a known label's casing; leave unknowns as-is
    (the BI engine reports them). Prevents 'mining' from missing 'Mining'."""
    if intent.sector:
        for known in schema.KNOWN_SECTORS:
            if intent.sector.strip().lower() == known.lower():
                intent.sector = known
                break
    return intent


def parse_intent(question: str, today: date | None = None) -> Intent:
    """LLM if configured (with graceful fallback), else deterministic."""
    if settings.llm_enabled:
        try:
            return _canonicalize_sector(parse_llm(question, today))
        except Exception:
            fallback = parse_rule_based(question, today)
            fallback.assumptions.append(
                "LLM intent parsing was unavailable; used the deterministic parser."
            )
            return _canonicalize_sector(fallback)
    return _canonicalize_sector(parse_rule_based(question, today))
