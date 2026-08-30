"""
Resilience + failure-boundary tests.

These assert the system degrades safely rather than crashing or fabricating:
  * monday client retries transient failures and maps errors to MondayError
  * the dataset layer serves a stale cache when a refresh fails
  * the agent returns a safe "error" (never numbers) when the data source is down
  * narration falls back to the deterministic template when the LLM fails
"""

from __future__ import annotations

import httpx
import pytest

from app import agent, datasource, monday_client
from app.monday_client import MondayClient, MondayError


class _Resp:
    def __init__(self, status_code=200, payload=None, bad_json=False):
        self.status_code = status_code
        self._payload = payload or {}
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._payload


def test_transient_5xx_is_retried_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_post(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Resp(status_code=503)          # transient -> retry
        return _Resp(payload={"data": {"ok": 1}})  # success

    monkeypatch.setattr(monday_client.httpx, "post", fake_post)
    c = MondayClient(token="t", retries=2, backoff=0)
    assert c._post("q", {}) == {"ok": 1}
    assert calls["n"] == 2


def test_network_error_exhausts_retries_and_raises(monkeypatch):
    def fake_post(*a, **k):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(monday_client.httpx, "post", fake_post)
    c = MondayClient(token="t", retries=1, backoff=0)
    with pytest.raises(MondayError):
        c._post("q", {})


def test_401_fails_fast_without_retry(monkeypatch):
    calls = {"n": 0}

    def fake_post(*a, **k):
        calls["n"] += 1
        return _Resp(status_code=401)

    monkeypatch.setattr(monday_client.httpx, "post", fake_post)
    c = MondayClient(token="t", retries=3, backoff=0)
    with pytest.raises(MondayError):
        c._post("q", {})
    assert calls["n"] == 1  # no retries on auth failure


def test_graphql_errors_do_not_leak_internals(monkeypatch):
    def fake_post(*a, **k):
        return _Resp(payload={"errors": [{"message": "secret internal detail"}]})

    monkeypatch.setattr(monday_client.httpx, "post", fake_post)
    c = MondayClient(token="t", retries=0, backoff=0)
    with pytest.raises(MondayError) as ei:
        c._post("q", {})
    assert "secret internal detail" not in str(ei.value)


def test_dataset_serves_stale_cache_on_refresh_failure(monkeypatch, dataset):
    datasource._cache["dataset"] = dataset  # seed a good snapshot
    monkeypatch.setattr(datasource, "_load_from_monday",
                        lambda: (_ for _ in ()).throw(MondayError("down")))
    ds = datasource.get_dataset(force_refresh=True)
    assert ds.source == "monday (stale cache)"
    assert ds.deals.shape[0] == dataset.deals.shape[0]


def test_agent_returns_safe_error_when_data_down(monkeypatch):
    monkeypatch.setattr(agent, "get_dataset",
                        lambda *a, **k: (_ for _ in ()).throw(MondayError("down")))
    resp = agent.answer("what is our win rate in mining?")
    assert resp["type"] == "error"
    assert "result" not in resp            # never emits numbers on failure
    assert "down" not in resp["answer"]    # raw detail not surfaced


def test_narration_falls_back_when_llm_fails(monkeypatch, dataset):
    from app import narrate
    from app.config import settings
    from app import bi_engine as bi

    settings.llm_provider = "groq"  # pretend an LLM is configured
    monkeypatch.setattr(settings, "groq_api_key", "x", raising=False)

    class Boom:
        name = "groq"
        def complete(self, *a, **k):
            raise RuntimeError("llm down")

    monkeypatch.setattr(narrate, "get_provider", lambda: Boom(), raising=False)
    # get_provider is imported lazily inside llm_narrative; patch the source too.
    from app import llm
    monkeypatch.setattr(llm, "get_provider", lambda: Boom())

    result = bi.win_rate(dataset, sector="Mining")
    text = narrate.narrate("win rate in mining?", result)
    assert text  # deterministic template still produced an answer
    settings.llm_provider = "none"
