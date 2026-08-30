"""Data-quality / normalization tests — the messy-data contract."""

from __future__ import annotations

import numpy as np

from app import normalize
from tests.conftest import DEAL_ROWS, WO_ROWS


def test_exact_duplicate_removed_and_reported():
    df, q = normalize.normalize(DEAL_ROWS, "deals")
    # 6 raw rows, one is an exact business duplicate of "Beta".
    assert q.raw_count == 6
    assert q.duplicates_removed == 1
    assert q.clean_count == 5
    assert (df["name"] == "Beta").sum() == 1


def test_header_echo_category_becomes_missing():
    df, q = normalize.normalize(DEAL_ROWS, "deals")
    assert q.header_echo_cleaned == 1
    # "Sector/service" must not survive as a real sector.
    assert "Sector/service" not in set(df["sector"].dropna())


def test_missing_number_stays_missing_not_zero():
    df, _ = normalize.normalize(DEAL_ROWS, "deals")
    delta = df[df["name"] == "Delta"].iloc[0]
    assert np.isnan(delta["deal_value"])  # blank -> NaN, never 0


def test_negative_amounts_preserved_and_counted():
    df, q = normalize.normalize(WO_ROWS, "work_orders")
    assert q.negatives.get("billed_value") == 1
    assert float(df[df["name"] == "Gamma"]["billed_value"].iloc[0]) == -100.0


def test_coverage_reported():
    _, q = normalize.normalize(DEAL_ROWS, "deals")
    # deal_value present on 4 of 5 clean rows (Delta missing) -> 80%.
    assert round(q.coverage["deal_value"]) == 80


def test_dates_parsed_to_datetime():
    df, _ = normalize.normalize(DEAL_ROWS, "deals")
    beta = df[df["name"] == "Beta"].iloc[0]
    assert str(beta["tentative_close_date"].date()) == "2026-03-01"
