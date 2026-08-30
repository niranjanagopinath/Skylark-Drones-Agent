"""
Deterministic BI engine.

Every business number the user sees is computed here, in plain Python/pandas —
never by the LLM. Each metric returns a `MetricResult` that carries:
  * summary_values : the headline numbers
  * breakdown      : optional per-group rows
  * caveats        : data-quality warnings relevant to THIS metric
  * audit          : filters applied, denominators, counts, coverage — so the
                     number can be independently reproduced and explained.

Business definitions and assumptions are documented inline and in DECISION_LOG.md.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from . import schema
from .datasource import Dataset

# ---------------------------------------------------------------------------
# Assumptions (documented in DECISION_LOG.md)
# ---------------------------------------------------------------------------
# Probability-weighted pipeline uses these factors. These are an explicit
# assumption (the data only gives High/Medium/Low, not numeric probabilities).
PROBABILITY_WEIGHTS = {"High": 0.8, "Medium": 0.5, "Low": 0.2}

# "Open pipeline" = deals that are neither Won nor Dead.
_OPEN_EXCLUDED_STATUS = schema.TERMINAL_LOST_STATUS | schema.TERMINAL_WON_STATUS

COVERAGE_WARN_THRESHOLD = 75.0  # warn when a field used by a metric is <75% present


@dataclass
class MetricResult:
    metric: str
    title: str
    summary_values: dict[str, Any] = field(default_factory=dict)
    breakdown: list[dict[str, Any]] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    audit: dict[str, Any] = field(default_factory=dict)
    unit: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Filtering helpers
# ---------------------------------------------------------------------------
def _filter_sector(df: pd.DataFrame, sector: str | None) -> tuple[pd.DataFrame, str | None]:
    if not sector:
        return df, None
    mask = df["sector"].fillna("").str.strip().str.lower() == sector.strip().lower()
    return df[mask].copy(), sector


def _filter_dates(
    df: pd.DataFrame, date_field: str, start: str | None, end: str | None
) -> tuple[pd.DataFrame, dict | None]:
    if not start and not end:
        return df, None
    if date_field not in df.columns:
        return df, None
    col = pd.to_datetime(df[date_field], errors="coerce")
    mask = pd.Series(True, index=df.index)
    if start:
        mask &= col >= pd.Timestamp(start)
    if end:
        mask &= col <= pd.Timestamp(end)
    return df[mask].copy(), {"field": date_field, "start": start, "end": end}


def _empty_timeframe_caveat(pre_filter_df: pd.DataFrame, date_field: str,
                            date_filter: dict | None, n_after: int) -> list[str]:
    """When a timeframe filter yields nothing, explain the data's real date range."""
    if not date_filter or n_after > 0:
        return []
    dr = pd.to_datetime(pre_filter_df[date_field], errors="coerce").dropna()
    if dr.empty:
        return [f"No records fall in the requested window "
                f"({date_filter['start']}–{date_filter['end']}), and "
                f"'{date_field}' is empty for this selection."]
    return [
        f"No records fall in the requested window "
        f"({date_filter['start']}–{date_filter['end']}). For context, "
        f"'{date_field}' in this selection ranges "
        f"{dr.min().date()} to {dr.max().date()}."
    ]


def _coverage_caveats(quality, fields: list[str]) -> list[str]:
    out = []
    for f in fields:
        cov = quality.coverage.get(f)
        if cov is not None and cov < COVERAGE_WARN_THRESHOLD:
            out.append(
                f"'{f}' is only {cov:.0f}% populated — this figure covers the "
                f"subset of records that have it."
            )
    return out


def _sum(series: pd.Series) -> float:
    return float(series.dropna().sum())


def _known_sectors(ds: Dataset) -> list[str]:
    vals = pd.concat([ds.deals["sector"], ds.work_orders["sector"]]).dropna().unique()
    return sorted(str(v) for v in vals)


def _unknown_sector_caveats(ds: Dataset, df_sec: pd.DataFrame, sec: str | None) -> list[str]:
    """If a sector filter matched nothing, say so and list the sectors we do have."""
    if not sec or len(df_sec) > 0:
        return []
    return [
        f"No records match the sector '{sec}'. Known sectors are: "
        + ", ".join(_known_sectors(ds)) + "."
    ]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def pipeline_health(ds: Dataset, sector: str | None = None,
                    start: str | None = None, end: str | None = None) -> MetricResult:
    df_sec, sec = _filter_sector(ds.deals, sector)
    df, date_filter = _filter_dates(df_sec, "tentative_close_date", start, end)

    total = len(df)
    open_df = df[~df["deal_status"].fillna("").isin(_OPEN_EXCLUDED_STATUS)]
    won = df[df["deal_status"] == "Won"]
    lost = df[df["deal_status"] == "Dead"]

    open_value = _sum(open_df["deal_value"])
    open_value_n = int(open_df["deal_value"].notna().sum())

    # Probability-weighted pipeline over open deals having both value + probability.
    weighted = 0.0
    weighted_n = 0
    for _, r in open_df.iterrows():
        w = PROBABILITY_WEIGHTS.get(r.get("closure_probability"))
        v = r.get("deal_value")
        if w is not None and pd.notna(v):
            weighted += w * float(v)
            weighted_n += 1

    caveats = _unknown_sector_caveats(ds, df_sec, sec)
    caveats += _empty_timeframe_caveat(df_sec, "tentative_close_date", date_filter, total)
    caveats += _coverage_caveats(ds.deals_quality, ["deal_value", "closure_probability"])
    if weighted_n:
        caveats.append(
            f"Weighted pipeline uses assumed factors High={PROBABILITY_WEIGHTS['High']}, "
            f"Medium={PROBABILITY_WEIGHTS['Medium']}, Low={PROBABILITY_WEIGHTS['Low']} "
            f"over the {weighted_n} open deal(s) that have both a value and a probability."
        )

    return MetricResult(
        metric="pipeline_health",
        title="Pipeline health" + (f" — {sec}" if sec else ""),
        summary_values={
            "total_deals": total,
            "open_deals": len(open_df),
            "won_deals": len(won),
            "lost_deals": len(lost),
            "open_pipeline_value_inr": round(open_value, 2),
            "weighted_pipeline_value_inr": round(weighted, 2),
        },
        caveats=caveats,
        audit={
            "sector_filter": sec,
            "date_filter": date_filter,
            "open_pipeline_definition": "deal_status not in {Won, Dead}",
            "open_value_from_records": open_value_n,
            "open_deals_total": len(open_df),
            "deal_value_coverage_pct": ds.deals_quality.coverage.get("deal_value"),
        },
        unit="INR / count",
    )


def revenue_summary(ds: Dataset, sector: str | None = None,
                    start: str | None = None, end: str | None = None) -> MetricResult:
    df_sec, sec = _filter_sector(ds.work_orders, sector)
    df, date_filter = _filter_dates(df_sec, "start_date", start, end)

    order = _sum(df["order_value"])
    billed = _sum(df["billed_value"])
    collected = _sum(df["collected_amount"])
    receivable = _sum(df["amount_receivable"])
    to_be_billed = _sum(df["amount_to_be_billed"])

    billing_eff = (billed / order) if order else None
    collection_eff = (collected / billed) if billed else None

    caveats = _unknown_sector_caveats(ds, df_sec, sec)
    caveats += _empty_timeframe_caveat(df_sec, "start_date", date_filter, len(df))
    caveats += _coverage_caveats(
        ds.wo_quality, ["order_value", "billed_value", "collected_amount"]
    )
    if ds.wo_quality.negatives:
        caveats.append(
            "Some amounts are negative (credit notes / over-collection adjustments) "
            "and are included as-is in these totals."
        )

    return MetricResult(
        metric="revenue_summary",
        title="Revenue & collections" + (f" — {sec}" if sec else ""),
        summary_values={
            "work_orders": len(df),
            "order_value_inr": round(order, 2),
            "billed_value_inr": round(billed, 2),
            "collected_amount_inr": round(collected, 2),
            "amount_receivable_inr": round(receivable, 2),
            "amount_to_be_billed_inr": round(to_be_billed, 2),
            "billing_efficiency_pct": round(100 * billing_eff, 1) if billing_eff is not None else None,
            "collection_efficiency_pct": round(100 * collection_eff, 1) if collection_eff is not None else None,
        },
        caveats=caveats,
        audit={
            "sector_filter": sec,
            "date_filter": date_filter,
            "billing_efficiency_definition": "sum(billed_value) / sum(order_value)",
            "collection_efficiency_definition": "sum(collected_amount) / sum(billed_value)",
            "collected_coverage_pct": ds.wo_quality.coverage.get("collected_amount"),
            "records_in_scope": len(df),
        },
        unit="INR / percent",
    )


def win_rate(ds: Dataset, sector: str | None = None) -> MetricResult:
    df, sec = _filter_sector(ds.deals, sector)
    won = int((df["deal_status"] == "Won").sum())
    lost = int((df["deal_status"] == "Dead").sum())
    closed = won + lost
    rate = (won / closed) if closed else None

    caveats = _unknown_sector_caveats(ds, df, sec)
    if closed == 0 and not caveats:
        caveats.append("No closed deals (Won/Dead) in scope, so win rate is undefined.")

    return MetricResult(
        metric="win_rate",
        title="Win rate" + (f" — {sec}" if sec else ""),
        summary_values={
            "won": won,
            "lost": lost,
            "closed_total": closed,
            "win_rate_pct": round(100 * rate, 1) if rate is not None else None,
        },
        caveats=caveats,
        audit={
            "sector_filter": sec,
            "win_rate_definition": "Won / (Won + Dead)",
            "note": "Open / On Hold deals are excluded from the denominator.",
        },
        unit="percent",
    )


def sector_performance(ds: Dataset) -> MetricResult:
    """Cross-board view: one row per sector, combining deals + work orders."""
    sectors = _known_sectors(ds)
    rows = []
    for s in sectors:
        d = ds.deals[ds.deals["sector"] == s]
        w = ds.work_orders[ds.work_orders["sector"] == s]
        won = int((d["deal_status"] == "Won").sum())
        lost = int((d["deal_status"] == "Dead").sum())
        closed = won + lost
        rows.append({
            "sector": s,
            "deals": len(d),
            "won": won,
            "win_rate_pct": round(100 * won / closed, 1) if closed else None,
            "open_pipeline_value_inr": round(
                _sum(d[~d["deal_status"].fillna("").isin(_OPEN_EXCLUDED_STATUS)]["deal_value"]), 2),
            "work_orders": len(w),
            "billed_value_inr": round(_sum(w["billed_value"]), 2),
            "collected_amount_inr": round(_sum(w["collected_amount"]), 2),
        })
    rows.sort(key=lambda r: r["billed_value_inr"], reverse=True)

    caveats = _coverage_caveats(ds.deals_quality, ["deal_value"])
    caveats.append(
        "Sectors present in Deals but absent from Work Orders (or vice-versa) show "
        "zero on the missing side — this reflects real coverage, not a data error."
    )

    return MetricResult(
        metric="sector_performance",
        title="Sector performance (deals + work orders)",
        breakdown=rows,
        caveats=caveats,
        audit={
            "sectors_considered": sectors,
            "join": "deals and work_orders aggregated independently per sector label",
        },
        unit="mixed",
    )


def deal_status_breakdown(ds: Dataset, sector: str | None = None) -> MetricResult:
    df, sec = _filter_sector(ds.deals, sector)
    counts = df["deal_status"].fillna("(missing)").value_counts()
    rows = [{"status": k, "deals": int(v)} for k, v in counts.items()]
    return MetricResult(
        metric="deal_status_breakdown",
        title="Deals by status" + (f" — {sec}" if sec else ""),
        summary_values={"total_deals": len(df)},
        breakdown=rows,
        audit={"sector_filter": sec},
        unit="count",
    )


def stage_breakdown(ds: Dataset, sector: str | None = None) -> MetricResult:
    df, sec = _filter_sector(ds.deals, sector)
    counts = df["deal_stage"].fillna("(missing)").value_counts()
    rows = [{"stage": k, "deals": int(v)} for k, v in counts.items()]
    return MetricResult(
        metric="stage_breakdown",
        title="Deals by funnel stage" + (f" — {sec}" if sec else ""),
        summary_values={"total_deals": len(df)},
        breakdown=rows,
        audit={"sector_filter": sec},
        unit="count",
    )


def collections_summary(ds: Dataset, sector: str | None = None) -> MetricResult:
    df, sec = _filter_sector(ds.work_orders, sector)
    billed = _sum(df["billed_value"])
    collected = _sum(df["collected_amount"])
    receivable = _sum(df["amount_receivable"])
    eff = (collected / billed) if billed else None
    caveats = _unknown_sector_caveats(ds, df, sec)
    caveats += _coverage_caveats(ds.wo_quality, ["collected_amount", "billed_value"])
    return MetricResult(
        metric="collections_summary",
        title="Collections & receivables" + (f" — {sec}" if sec else ""),
        summary_values={
            "billed_value_inr": round(billed, 2),
            "collected_amount_inr": round(collected, 2),
            "outstanding_receivable_inr": round(receivable, 2),
            "collection_efficiency_pct": round(100 * eff, 1) if eff is not None else None,
        },
        caveats=caveats,
        audit={"sector_filter": sec,
               "collection_efficiency_definition": "sum(collected)/sum(billed)"},
        unit="INR / percent",
    )


def data_quality(ds: Dataset) -> MetricResult:
    return MetricResult(
        metric="data_quality",
        title="Data quality overview",
        summary_values={
            "deals": ds.deals_quality.to_dict(),
            "work_orders": ds.wo_quality.to_dict(),
            "source": ds.source,
            "monday_account": ds.account,
        },
        caveats=list(ds.deals_quality.notes) + list(ds.wo_quality.notes),
        unit="report",
    )


def leadership_update(ds: Dataset, start: str | None = None,
                      end: str | None = None) -> MetricResult:
    """
    Composite executive snapshot: pipeline + revenue + top sectors + the caveats
    a leader should know before quoting these numbers. This is our interpretation
    of the optional "help prepare data for leadership updates" requirement.
    """
    pipe = pipeline_health(ds, start=start, end=end).summary_values
    rev = revenue_summary(ds, start=start, end=end).summary_values
    sect = sector_performance(ds)
    top_sectors = sect.breakdown[:3]

    caveats = sorted(set(
        pipeline_health(ds, start=start, end=end).caveats
        + revenue_summary(ds, start=start, end=end).caveats
    ))
    # Flat headline numbers so the answer renders richly and the numeric guard
    # can validate every figure the narrator might cite.
    return MetricResult(
        metric="leadership_update",
        title="Leadership update",
        summary_values={
            "open_pipeline_value_inr": pipe["open_pipeline_value_inr"],
            "open_deals": pipe["open_deals"],
            "won_deals": pipe["won_deals"],
            "lost_deals": pipe["lost_deals"],
            "order_value_inr": rev["order_value_inr"],
            "billed_value_inr": rev["billed_value_inr"],
            "collected_amount_inr": rev["collected_amount_inr"],
            "amount_receivable_inr": rev["amount_receivable_inr"],
            "collection_efficiency_pct": rev["collection_efficiency_pct"],
        },
        breakdown=top_sectors,
        caveats=caveats,
        audit={
            "components": ["pipeline_health", "revenue_summary", "sector_performance"],
            "date_filter": {"start": start, "end": end},
        },
        unit="mixed",
    )


# ---------------------------------------------------------------------------
# Registry: intent metric name -> callable(ds, **params)
# ---------------------------------------------------------------------------
METRICS = {
    "pipeline_health": pipeline_health,
    "revenue_summary": revenue_summary,
    "win_rate": win_rate,
    "sector_performance": sector_performance,
    "deal_status_breakdown": deal_status_breakdown,
    "stage_breakdown": stage_breakdown,
    "collections_summary": collections_summary,
    "data_quality": data_quality,
    "leadership_update": leadership_update,
}
