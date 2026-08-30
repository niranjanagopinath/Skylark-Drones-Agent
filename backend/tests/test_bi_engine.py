"""
BI-engine correctness tests.

Each expected value is computed by hand from the fixture in conftest.py, so a
passing test literally demonstrates "the number shown to the user can be
independently verified."
"""

from __future__ import annotations

from app import bi_engine as bi


def test_pipeline_health_counts_and_values(dataset):
    r = bi.pipeline_health(dataset)
    v = r.summary_values
    # Clean deals: Alpha(Won), Beta(Open), Gamma(Dead), Delta(Open), Echo(Open) = 5
    assert v["total_deals"] == 5
    assert v["open_deals"] == 3          # Beta, Delta, Echo
    assert v["won_deals"] == 1
    assert v["lost_deals"] == 1
    # Open pipeline value = Beta 200000 + Echo 300000 (Delta value missing) = 500000
    assert v["open_pipeline_value_inr"] == 500000.0
    # Weighted = only Beta has value+probability: 0.5 * 200000 = 100000
    assert v["weighted_pipeline_value_inr"] == 100000.0


def test_pipeline_health_sector_filter(dataset):
    r = bi.pipeline_health(dataset, sector="Mining")
    v = r.summary_values
    # Mining clean deals: Alpha(Won), Beta(Open)
    assert v["total_deals"] == 2
    assert v["open_deals"] == 1
    assert v["open_pipeline_value_inr"] == 200000.0


def test_win_rate(dataset):
    r = bi.win_rate(dataset)
    v = r.summary_values
    assert v["won"] == 1 and v["lost"] == 1 and v["closed_total"] == 2
    assert v["win_rate_pct"] == 50.0


def test_win_rate_undefined_for_unknown_sector(dataset):
    r = bi.win_rate(dataset, sector="DoesNotExist")
    assert r.summary_values["win_rate_pct"] is None
    # Unknown sector is explained by listing the real sectors.
    assert any("No records match the sector" in c for c in r.caveats)


def test_revenue_summary_totals_and_efficiency(dataset):
    r = bi.revenue_summary(dataset)
    v = r.summary_values
    assert v["order_value_inr"] == 3500.0           # 1000+2000+500
    assert v["billed_value_inr"] == 1700.0          # 800+1000-100
    assert v["collected_amount_inr"] == 400.0       # 400+0 (Beta missing)
    assert v["amount_receivable_inr"] == 1300.0     # 400+1000-100
    # billing efficiency = 1700/3500 = 48.57 -> 48.6
    assert v["billing_efficiency_pct"] == 48.6
    # collection efficiency = 400/1700 = 23.53 -> 23.5
    assert v["collection_efficiency_pct"] == 23.5


def test_revenue_summary_warns_on_negatives(dataset):
    r = bi.revenue_summary(dataset)
    assert any("negative" in c.lower() for c in r.caveats)


def test_sector_performance_rows(dataset):
    r = bi.sector_performance(dataset)
    by_sector = {row["sector"]: row for row in r.breakdown}
    assert set(by_sector) == {"Mining", "Renewables"}
    assert by_sector["Mining"]["deals"] == 2
    assert by_sector["Mining"]["won"] == 1
    # Mining billed = Alpha 800 + Gamma -100 = 700
    assert by_sector["Mining"]["billed_value_inr"] == 700.0


def test_metric_result_is_json_serializable(dataset):
    import json
    r = bi.pipeline_health(dataset)
    json.dumps(r.to_dict())  # must not raise


def test_numeric_guard_rejects_fabricated_numbers(dataset):
    """The narration guard must reject any number not derivable from the result."""
    from app import narrate
    r = bi.collections_summary(dataset)  # has billed/collected/receivable, NO win rate
    grounded = "Collections stand at " + narrate.format_inr(
        r.summary_values["collected_amount_inr"]) + "."
    fabricated = "Our win rate is 55.6% and collections look healthy."
    assert narrate.narrative_is_grounded(grounded, r) is True
    assert narrate.narrative_is_grounded(fabricated, r) is False


def test_unknown_sector_lists_known_sectors(dataset):
    r = bi.pipeline_health(dataset, sector="Healthcare")  # not in fixture
    assert r.summary_values["total_deals"] == 0
    assert any("No records match the sector 'Healthcare'" in c for c in r.caveats)
    assert any("Mining" in c and "Renewables" in c for c in r.caveats)


def test_empty_timeframe_explains_date_range(dataset):
    # Fixture deals close in 2026; a 2099 window must return 0 with an explanation.
    r = bi.pipeline_health(dataset, start="2099-01-01", end="2099-12-31")
    assert r.summary_values["total_deals"] == 0
    assert any("requested window" in c for c in r.caveats)
