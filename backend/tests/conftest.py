"""
Shared test fixtures.

We build a tiny, hand-verifiable dataset that deliberately contains the messy
cases the system must handle: an exact duplicate deal, a header-echo category,
missing numbers, and a negative amount. Because the inputs are known, every
expected BI number can be computed by hand — that is the whole point: the figures
the agent reports are independently verifiable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make `import app...` work when tests run from the repo root or backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import normalize  # noqa: E402
from app.datasource import Dataset  # noqa: E402

DEAL_ROWS = [
    # name, sector, status, stage, probability, value, tentative_close_date
    {"name": "Alpha", "sector": "Mining", "deal_status": "Won",
     "deal_stage": "H. Work Order Received", "closure_probability": "High",
     "deal_value": "100000", "tentative_close_date": "2026-02-01"},
    {"name": "Beta", "sector": "Mining", "deal_status": "Open",
     "closure_probability": "Medium", "deal_value": "200000",
     "tentative_close_date": "2026-03-01"},
    {"name": "Gamma", "sector": "Renewables", "deal_status": "Dead",
     "deal_value": "50000"},
    {"name": "Delta", "sector": "Renewables", "deal_status": "Open",
     "closure_probability": "Low", "deal_value": ""},          # missing value
    {"name": "Beta", "sector": "Mining", "deal_status": "Open",  # EXACT dup of Beta
     "closure_probability": "Medium", "deal_value": "200000",
     "tentative_close_date": "2026-03-01"},
    {"name": "Echo", "sector": "Sector/service", "deal_status": "Open",  # header echo
     "deal_value": "300000"},
]

WO_ROWS = [
    {"name": "Alpha", "sector": "Mining", "order_value": "1000",
     "billed_value": "800", "collected_amount": "400",
     "amount_receivable": "400", "amount_to_be_billed": "200"},
    {"name": "Beta", "sector": "Renewables", "order_value": "2000",
     "billed_value": "1000", "collected_amount": "",           # missing collected
     "amount_receivable": "1000", "amount_to_be_billed": "1000"},
    {"name": "Gamma", "sector": "Mining", "order_value": "500",
     "billed_value": "-100", "collected_amount": "0",          # negative billed
     "amount_receivable": "-100", "amount_to_be_billed": "600"},
]


@pytest.fixture
def dataset() -> Dataset:
    deals_df, deals_q = normalize.normalize(DEAL_ROWS, "deals")
    wo_df, wo_q = normalize.normalize(WO_ROWS, "work_orders")
    import time
    return Dataset(
        deals=deals_df, work_orders=wo_df,
        deals_quality=deals_q, wo_quality=wo_q,
        loaded_at=time.monotonic(), source="fixture",
    )
