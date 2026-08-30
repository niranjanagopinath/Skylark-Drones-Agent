"""
Normalization + data-quality layer.

Input: raw rows as logical-keyed dicts (produced by mapping monday column ids to
logical names). Output: a cleaned pandas DataFrame plus a structured
`DataQualityReport` describing exactly what we changed and what remains uncertain.

Guiding rules (see DECISION_LOG.md):
  * Missing stays missing. We never coerce a blank number to 0 — that would
    silently change the meaning of a sum or an average.
  * Duplicates are removed only when EVERY business field matches; the count is
    always reported, never hidden.
  * Categories get whitespace/case fixes and header-echo removal only. We do not
    merge distinct real categories.
  * Negative amounts are preserved (they are real credit notes / adjustments) but
    counted, so the user can be warned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from . import schema


@dataclass
class DataQualityReport:
    board: str
    raw_count: int
    clean_count: int
    duplicates_removed: int = 0
    header_echo_cleaned: int = 0
    coverage: dict[str, float] = field(default_factory=dict)  # logical -> % present
    negatives: dict[str, int] = field(default_factory=dict)   # money field -> count
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "board": self.board,
            "raw_count": self.raw_count,
            "clean_count": self.clean_count,
            "duplicates_removed": self.duplicates_removed,
            "header_echo_cleaned": self.header_echo_cleaned,
            "coverage": {k: round(v, 1) for k, v in self.coverage.items()},
            "negatives": self.negatives,
            "notes": list(self.notes),
        }


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _clean_category(value: Any) -> str | None:
    """Whitespace-normalize a category and drop header-echo artifacts."""
    s = _clean_str(value)
    if s is None:
        return None
    if s.lower() in schema.HEADER_ECHO_TOKENS:
        return None
    return s


def _to_number(value: Any) -> float | None:
    s = _clean_str(value)
    if s is None:
        return None
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _to_datetime(value: Any) -> pd.Timestamp | None:
    s = _clean_str(value)
    if s is None:
        return None
    ts = pd.to_datetime(s, errors="coerce", format="mixed")
    return None if pd.isna(ts) else ts


# ---------------------------------------------------------------------------
# Board field groupings
# ---------------------------------------------------------------------------
_BOARD_FIELDS = {
    "deals": {
        "money": schema.DEALS_MONEY,
        "dates": schema.DEALS_DATES,
        "categorical": schema.DEALS_CATEGORICAL,
        "text": schema.DEALS_TEXT,
    },
    "work_orders": {
        "money": schema.WO_MONEY,
        "dates": schema.WO_DATES,
        "categorical": schema.WO_CATEGORICAL,
        "text": schema.WO_TEXT,
    },
}


def normalize(rows: list[dict[str, Any]], board: str) -> tuple[pd.DataFrame, DataQualityReport]:
    """
    Clean raw logical-keyed rows for a board.

    `rows` must include a "name" key plus any subset of the board's logical
    fields. Absent fields are treated as missing.
    """
    if board not in _BOARD_FIELDS:
        raise ValueError(f"unknown board '{board}'")
    fields = _BOARD_FIELDS[board]
    raw_count = len(rows)

    df = pd.DataFrame(rows)
    # Ensure every expected column exists so downstream code is uniform.
    all_cols = ["name"] + fields["money"] + fields["dates"] + fields["categorical"] + fields["text"]
    for col in all_cols:
        if col not in df.columns:
            df[col] = None
    df = df[[c for c in all_cols if c in df.columns] +
            [c for c in df.columns if c not in all_cols]]

    report = DataQualityReport(board=board, raw_count=raw_count, clean_count=raw_count)

    # --- name + text ---
    df["name"] = df["name"].map(_clean_str)
    for col in fields["text"]:
        df[col] = df[col].map(_clean_str)

    # --- categorical (with header-echo cleaning) ---
    echo_before = 0
    for col in fields["categorical"]:
        present_before = df[col].map(lambda v: _clean_str(v) is not None).sum()
        df[col] = df[col].map(_clean_category)
        present_after = df[col].notna().sum()
        echo_before += int(present_before - present_after)
    report.header_echo_cleaned = echo_before
    if echo_before:
        report.notes.append(
            f"Removed {echo_before} header-echo category value(s) (spreadsheet "
            f"artifacts) by setting them to missing."
        )

    # --- money ---
    for col in fields["money"]:
        df[col] = df[col].map(_to_number)
        neg = int((df[col] < 0).sum())
        if neg:
            report.negatives[col] = neg

    # --- dates ---
    for col in fields["dates"]:
        df[col] = df[col].map(_to_datetime)

    # --- duplicate removal (exact business-field match) ---
    business_cols = [c for c in all_cols if c != "source_row"]
    before = len(df)
    df = df.drop_duplicates(subset=business_cols, keep="first").reset_index(drop=True)
    removed = before - len(df)
    report.duplicates_removed = removed
    if removed:
        report.notes.append(
            f"Removed {removed} exact-duplicate row(s) (identical across all "
            f"business fields); kept the first occurrence."
        )

    report.clean_count = len(df)

    # --- coverage (% non-missing) for the fields that matter ---
    for col in fields["money"] + fields["dates"] + fields["categorical"]:
        cov = 100.0 * df[col].notna().sum() / len(df) if len(df) else 0.0
        report.coverage[col] = cov

    if report.negatives:
        report.notes.append(
            "Negative amounts present (credit notes / adjustments) and preserved: "
            + ", ".join(f"{k}={v}" for k, v in report.negatives.items())
        )

    return df, report
