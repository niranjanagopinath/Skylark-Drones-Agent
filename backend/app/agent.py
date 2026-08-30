"""
Agent orchestration.

Pipeline:  question -> intent -> (clarify?) -> deterministic compute -> narrate.

This is where the "AI vs arithmetic" wall lives: the LLM only shapes the intent
and the final prose; the numbers come exclusively from bi_engine. Failures at any
external dependency (monday, LLM) degrade to a safe, honest response rather than a
fabricated answer.
"""

from __future__ import annotations

import inspect
from datetime import date, datetime, timezone

from . import bi_engine, intent as intent_mod, narrate
from .datasource import Dataset, get_dataset
from .monday_client import MondayError


def _call_metric(name: str, ds: Dataset, sector: str | None,
                 start: str | None, end: str | None) -> bi_engine.MetricResult:
    fn = bi_engine.METRICS[name]
    params = inspect.signature(fn).parameters
    kwargs = {}
    if "sector" in params:
        kwargs["sector"] = sector
    if "start" in params:
        kwargs["start"] = start
    if "end" in params:
        kwargs["end"] = end
    return fn(ds, **kwargs)


def _data_source_meta(ds: Dataset) -> dict:
    return {
        "source": ds.source,
        "monday_account": ds.account,
        "age_seconds": round(ds.age_seconds, 1),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


def answer(question: str, today: date | None = None) -> dict:
    question = (question or "").strip()
    if not question:
        return {
            "type": "clarification",
            "answer": "What would you like to know? For example: "
                      "\"How's our pipeline in mining this quarter?\"",
            "intent": None,
        }

    parsed = intent_mod.parse_intent(question, today)

    # Ambiguous / unsupported -> ask, never guess a number.
    if parsed.needs_clarification or parsed.metric == "unsupported":
        return {
            "type": "clarification",
            "answer": parsed.clarification or
                      "Could you clarify what you'd like to know?",
            "intent": parsed.to_dict(),
            "assumptions": parsed.assumptions,
        }

    # Fetch data (graceful on monday failure).
    try:
        ds = get_dataset()
    except MondayError as exc:
        return {
            "type": "error",
            "answer": (
                "I can't reach the monday.com data source right now, so I won't "
                "guess. Please try again shortly. "
                f"(Details: {exc})"
            ),
            "intent": parsed.to_dict(),
        }

    tf = parsed.timeframe or {}
    result = _call_metric(
        parsed.metric, ds, parsed.sector, tf.get("start"), tf.get("end")
    )

    prose = narrate.narrate(question, result)

    # Merge intent-level assumptions (e.g. energy->Renewables, FY interpretation).
    assumptions = list(parsed.assumptions)
    if parsed.timeframe and parsed.timeframe.get("label"):
        assumptions.append(f"Timeframe interpreted as {parsed.timeframe['label']}.")

    return {
        "type": "answer",
        "answer": prose,
        "intent": parsed.to_dict(),
        "result": result.to_dict(),
        "caveats": result.caveats,
        "assumptions": assumptions,
        "data_source": _data_source_meta(ds),
    }
