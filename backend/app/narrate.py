"""
Answer narration.

Turns a computed `MetricResult` into a short, founder-readable answer. The LLM
path is given ONLY the numbers the BI engine produced and is explicitly told not
to invent or recompute anything; the deterministic template path is always
available as a fallback and for LLM-free deployments.
"""

from __future__ import annotations

import json
import re

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
    "2–4 sentence answer to the user's question using ONLY the numbers present in "
    "the Result JSON. NEVER invent, recompute, estimate, or extrapolate a number. "
    "If the user's question asks about a metric that is NOT in the Result JSON "
    "(e.g. they asked for win rate but the result only has collections), do NOT "
    "state a figure for it — instead add one short sentence saying that metric "
    "wasn't part of this result and can be pulled separately. Format money in "
    "Indian style (crore/lakh). Weave in the most important caveat so the reader "
    "trusts the figure appropriately. Be direct and useful, not verbose."
)


# ---------------------------------------------------------------------------
# Numeric guard: guarantee the narrator never surfaces a number that isn't in
# the computed result. If it does, we discard the LLM prose and fall back to the
# deterministic template. This is the safety net behind "trustworthy numbers".
# ---------------------------------------------------------------------------
def _collect_allowed(result: MetricResult) -> set[float]:
    allowed: set[float] = set()

    def add(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return
        for x in {f, round(f, 1), round(f, 2), round(f)}:
            allowed.add(float(x))
        a = abs(f)
        if a >= 1e5:
            allowed.add(round(a / 1e5, 2)); allowed.add(round(a / 1e5, 1))
        if a >= 1e7:
            allowed.add(round(a / 1e7, 2)); allowed.add(round(a / 1e7, 1))

    def walk(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
        elif isinstance(obj, (int, float)):
            add(obj)

    walk(result.summary_values)
    walk(result.breakdown)
    # Numbers mentioned in caveats (e.g. coverage "50%") are legitimate to cite.
    for c in result.caveats:
        for tok in re.findall(r"-?\d[\d,]*\.?\d*", c):
            add(tok.replace(",", ""))
    return allowed


def _numbers_in(text: str) -> list[float]:
    out = []
    for tok in re.findall(r"-?\d[\d,]*\.?\d*", text):
        try:
            out.append(float(tok.replace(",", "")))
        except ValueError:
            pass
    return out


def _is_allowed(n: float, allowed: set[float]) -> bool:
    if 2000 <= n <= 2099 and float(n).is_integer():  # years are safe to mention
        return True
    return any(abs(n - a) <= max(0.05, 0.02 * abs(a)) for a in allowed)


def narrative_is_grounded(text: str, result: MetricResult) -> bool:
    allowed = _collect_allowed(result)
    return all(_is_allowed(n, allowed) for n in _numbers_in(text))


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
            # Safety net: never surface a number the calculation didn't produce.
            if text and narrative_is_grounded(text, result):
                return text
        except Exception:
            pass
    return template_narrative(result)
