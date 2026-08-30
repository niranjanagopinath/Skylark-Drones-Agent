"""End-to-end agent tests over the fixture dataset (no monday, no LLM)."""

from __future__ import annotations

from datetime import date

from app import agent, datasource

TODAY = date(2026, 8, 30)


def _install(dataset):
    datasource._cache["dataset"] = dataset


def test_answer_pipeline_for_mining(dataset):
    _install(dataset)
    resp = agent.answer("How's our pipeline in mining?", TODAY)
    assert resp["type"] == "answer"
    assert resp["result"]["metric"] == "pipeline_health"
    assert resp["intent"]["sector"] == "Mining"
    assert resp["result"]["summary_values"]["open_pipeline_value_inr"] == 200000.0


def test_answer_revenue(dataset):
    _install(dataset)
    resp = agent.answer("what's our total billed revenue?", TODAY)
    assert resp["type"] == "answer"
    assert resp["result"]["summary_values"]["billed_value_inr"] == 1700.0
    # A caveat about low coverage / negatives should surface.
    assert resp["caveats"]


def test_unsupported_returns_clarification(dataset):
    _install(dataset)
    resp = agent.answer("what's the weather today?", TODAY)
    assert resp["type"] == "clarification"
    assert "result" not in resp  # never emits numbers when it can't answer


def test_energy_assumption_surfaced(dataset):
    _install(dataset)
    resp = agent.answer("pipeline for energy sector", TODAY)
    assert resp["type"] == "answer"
    assert any("energy" in a.lower() for a in resp["assumptions"])
