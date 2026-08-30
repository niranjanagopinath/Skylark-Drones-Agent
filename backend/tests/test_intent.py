"""Intent + timeframe tests (deterministic keyword path — no LLM required)."""

from __future__ import annotations

from datetime import date

from app import intent as I
from app.timeframe import resolve

TODAY = date(2026, 8, 30)


def test_timeframe_this_quarter():
    tf = resolve("this quarter", TODAY)
    assert tf["start"] == "2026-07-01" and tf["end"] == "2026-09-30"


def test_timeframe_last_quarter():
    tf = resolve("last quarter", TODAY)
    assert tf["start"] == "2026-04-01" and tf["end"] == "2026-06-30"


def test_timeframe_financial_year():
    tf = resolve("fy", TODAY)
    assert tf["start"] == "2026-04-01" and tf["end"] == "2027-03-31"


def test_timeframe_bare_year():
    tf = resolve("2025", TODAY)
    assert tf["start"] == "2025-01-01" and tf["end"] == "2025-12-31"


def test_pipeline_energy_this_quarter_maps_to_renewables():
    intent = I.parse_rule_based(
        "How's our pipeline looking for energy sector this quarter?", TODAY)
    assert intent.metric == "pipeline_health"
    assert intent.sector == "Renewables"
    assert any("energy" in a.lower() for a in intent.assumptions)
    assert intent.timeframe["label"] == "Q3 2026"


def test_revenue_in_mining():
    intent = I.parse_rule_based("what was our revenue in mining", TODAY)
    assert intent.metric == "revenue_summary"
    assert intent.sector == "Mining"


def test_win_rate_detected():
    assert I.parse_rule_based("what's our win rate?", TODAY).metric == "win_rate"


def test_sector_performance_detected():
    assert I.parse_rule_based("compare performance across sectors", TODAY).metric \
        == "sector_performance"


def test_collections_detected():
    assert I.parse_rule_based("how much is outstanding and uncollected", TODAY).metric \
        == "collections_summary"


def test_unsupported_question_asks_for_clarification():
    intent = I.parse_rule_based("what's the weather in Bangalore?", TODAY)
    assert intent.metric == "unsupported"
    assert intent.needs_clarification and intent.clarification
