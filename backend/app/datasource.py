"""
Data source: turns live monday boards into clean, cached DataFrames.

Responsibilities:
  1. Read board/column ids from board_config.json (produced by ingestion).
  2. Fetch raw items via MondayClient.
  3. Map monday's opaque column ids to logical field names.
  4. Normalize + build data-quality reports.
  5. Cache the result in memory with a TTL so a demo doesn't hammer the API and
     survives brief monday outages (served stale with a warning).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import pandas as pd

from . import normalize
from .config import load_board_config, settings
from .monday_client import MondayClient, MondayError


@dataclass
class Dataset:
    deals: pd.DataFrame
    work_orders: pd.DataFrame
    deals_quality: normalize.DataQualityReport
    wo_quality: normalize.DataQualityReport
    loaded_at: float
    source: str  # "monday" | "monday (stale cache)"
    account: str | None = None

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.loaded_at


_cache: dict[str, Dataset] = {}


def _invert_columns(columns: dict[str, str]) -> dict[str, str]:
    """{logical: monday_id} -> {monday_id: logical}."""
    return {mid: logical for logical, mid in columns.items()}


def _rows_from_items(items: list[dict], columns: dict[str, str]) -> list[dict]:
    id_to_logical = _invert_columns(columns)
    rows = []
    for it in items:
        row: dict[str, object] = {"name": it["name"]}
        for col_id, text in it["columns"].items():
            logical = id_to_logical.get(col_id)
            if logical and logical != "name":
                row[logical] = text
        rows.append(row)
    return rows


def _load_from_monday() -> Dataset:
    cfg = load_board_config()
    if not (cfg.get("deals") and cfg.get("work_orders")):
        raise MondayError(
            "board_config.json is missing or incomplete — run "
            "scripts/ingest_to_monday.py to create the monday boards first."
        )

    client = MondayClient()
    deals_items = client.fetch_items(cfg["deals"]["board_id"])
    wo_items = client.fetch_items(cfg["work_orders"]["board_id"])

    deals_rows = _rows_from_items(deals_items, cfg["deals"]["columns"])
    wo_rows = _rows_from_items(wo_items, cfg["work_orders"]["columns"])

    deals_df, deals_q = normalize.normalize(deals_rows, "deals")
    wo_df, wo_q = normalize.normalize(wo_rows, "work_orders")

    return Dataset(
        deals=deals_df,
        work_orders=wo_df,
        deals_quality=deals_q,
        wo_quality=wo_q,
        loaded_at=time.monotonic(),
        source="monday",
        account=cfg.get("monday_account"),
    )


def get_dataset(force_refresh: bool = False) -> Dataset:
    """
    Return the cached dataset, refreshing from monday when the TTL has expired.

    If a refresh fails but we have a previous copy, we serve the stale copy with
    a marked source rather than failing the user's query.
    """
    cached = _cache.get("dataset")
    fresh_enough = (
        cached is not None
        and not force_refresh
        and cached.age_seconds < settings.cache_ttl_seconds
    )
    if fresh_enough:
        return cached

    try:
        ds = _load_from_monday()
        _cache["dataset"] = ds
        return ds
    except MondayError:
        if cached is not None:
            # Degrade gracefully: reuse the last good snapshot.
            stale = Dataset(
                deals=cached.deals,
                work_orders=cached.work_orders,
                deals_quality=cached.deals_quality,
                wo_quality=cached.wo_quality,
                loaded_at=cached.loaded_at,
                source="monday (stale cache)",
                account=cached.account,
            )
            _cache["dataset"] = stale
            return stale
        raise


def set_fixture(deals: pd.DataFrame, work_orders: pd.DataFrame,
                deals_q: normalize.DataQualityReport,
                wo_q: normalize.DataQualityReport) -> None:
    """Inject a dataset directly (used by tests / offline mode)."""
    _cache["dataset"] = Dataset(
        deals=deals,
        work_orders=work_orders,
        deals_quality=deals_q,
        wo_quality=wo_q,
        loaded_at=time.monotonic(),
        source="fixture",
    )


def clear_cache() -> None:
    _cache.clear()
