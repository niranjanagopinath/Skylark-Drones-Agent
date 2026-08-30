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
# LLM parser (Anthropic structured tool-call)
# ---------------------------------------------------------------------------
_INTENT_TOOL = {
    "name": "set_intent",
    "description": "Record the structured intent of the user's BI question.",
    "input_schema": {
        "type": "object",
        "properties": {
            "metric": {
                "type": "string",
                "enum": SUPPORTED_METRICS + ["unsupported"],
                "description": "Which analysis best answers the question.",
            },
            "sector": {
                "type": ["string", "null"],
                "description": "Canonical sector to filter by, or null. Map 'energy' "
                               "to 'Renewables'. Known sectors include Mining, "
                               "Renewables, Railways, Powerline, Construction, Others.",
            },
            "timeframe_phrase": {
                "type": ["string", "null"],
                "description": "A relative timeframe phrase if present (e.g. 'this "
                               "quarter', 'last month', 'FY', '2026'), else null.",
            },
            "needs_clarification": {"type": "boolean"},
            "clarification": {
                "type": ["string", "null"],
                "description": "If ambiguous/unsupported, a short question to ask back.",
            },
        },
        "required": ["metric", "needs_clarification"],
    },
}

_SYSTEM = (
    "You classify founder-level business-intelligence questions for a company "
    "with two data sources: a sales Deals pipeline and Work Orders (execution + "
    "finance). Choose the single best metric. Do NOT compute or invent any "
    "numbers — only classify. If the question cannot be answered from deals/work "
    "orders data, set metric='unsupported' and provide a brief clarification."
)


def parse_llm(question: str, today: date | None = None) -> Intent:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=400,
        system=_SYSTEM,
        tools=[_INTENT_TOOL],
        tool_choice={"type": "tool", "name": "set_intent"},
        messages=[{"role": "user", "content": question}],
    )
    tool_use = next((b for b in resp.content if b.type == "tool_use"), None)
    if tool_use is None:
        raise ValueError("LLM did not return a tool call")
    data = tool_use.input
    if isinstance(data, str):
        data = json.loads(data)

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


def parse_intent(question: str, today: date | None = None) -> Intent:
    """LLM if configured (with graceful fallback), else deterministic."""
    if settings.llm_enabled:
        try:
            return parse_llm(question, today)
        except Exception:
            fallback = parse_rule_based(question, today)
            fallback.assumptions.append(
                "LLM intent parsing was unavailable; used the deterministic parser."
            )
            return fallback
    return parse_rule_based(question, today)
