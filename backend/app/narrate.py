"""
Answer narration.

Turns a computed `MetricResult` into a short, founder-readable answer. The LLM
path is given ONLY the numbers the BI engine produced and is explicitly told not
to invent or recompute anything; the deterministic template path is always
available as a fallback and for LLM-free deployments.
"""

from __future__ import annotations

import json

from .bi_engine import MetricResult
from .config import settings


# ---------------------------------------------------------------------------
# Indian-format currency helpers (crore / lakh)
# ---------------------------------------------------------------------------
def format_inr(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    v = float(value)
    sign = "-" if v < 0 else ""
    a = abs(v)
    if a >= 1e7:
        return f"{sign}₹{a / 1e7:.2f} Cr"
    if a >= 1e5:
        return f"{sign}₹{a / 1e5:.2f} L"
    return f"{sign}₹{a:,.0f}"


def _fmt_value(key: str, val) -> str:
    if val is None:
        return "n/a"
    if key.endswith("_inr"):
        return format_inr(val)
    if key.endswith("_pct"):
        return f"{val}%"
    return str(val)


# ---------------------------------------------------------------------------
# Deterministic template narration
# ---------------------------------------------------------------------------
def template_narrative(result: MetricResult) -> str:
    lines: list[str] = [f"**{result.title}**", ""]
    if result.summary_values:
        for k, v in result.summary_values.items():
            if isinstance(v, (dict, list)):
                continue
            label = k.replace("_inr", "").replace("_pct", "").replace("_", " ").capitalize()
            lines.append(f"- {label}: **{_fmt_value(k, v)}**")
    if result.breakdown:
        lines.append("")
        for row in result.breakdown[:8]:
            parts = []
            for k, v in row.items():
                if k in ("sector", "status", "stage"):
                    continue
                parts.append(f"{k.replace('_inr','').replace('_pct','').replace('_',' ')}: {_fmt_value(k, v)}")
            head = row.get("sector") or row.get("status") or row.get("stage") or ""
            lines.append(f"- **{head}** — " + ", ".join(parts))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM narration
# ---------------------------------------------------------------------------
_SYSTEM = (
    "You are a concise business-intelligence assistant for company leadership. "
    "You are given the RESULT of a deterministic calculation as JSON. Write a "
    "2–4 sentence answer to the user's question using ONLY the numbers provided. "
    "Never invent, recompute, or extrapolate numbers. Format money in Indian "
    "style (crore/lakh). If the result includes caveats, weave the most important "
    "one into the answer so the reader trusts the figure appropriately. Be direct "
    "and useful, not verbose."
)


def llm_narrative(question: str, result: MetricResult) -> str:
    from .llm import get_provider

    payload = {
        "question": question,
        "title": result.title,
        "summary_values": result.summary_values,
        "breakdown": result.breakdown[:8],
        "caveats": result.caveats,
    }
    user = f"Question: {question}\n\nResult JSON:\n{json.dumps(payload, default=str)}"
    return get_provider().complete(_SYSTEM, user, max_tokens=500).strip()


def narrate(question: str, result: MetricResult) -> str:
    if settings.llm_enabled:
        try:
            text = llm_narrative(question, result)
            if text:
                return text
        except Exception:
            pass
    return template_narrative(result)
