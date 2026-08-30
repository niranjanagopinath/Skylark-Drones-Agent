"""
Relative-timeframe resolution.

Turns phrases like "this quarter" into a concrete (start, end) ISO range,
computed against the real current date at runtime. Kept separate from the intent
parser so it is deterministic and unit-testable on its own.
"""

from __future__ import annotations

from datetime import date


def _quarter_start(y: int, q: int) -> date:
    return date(y, 3 * (q - 1) + 1, 1)


def _quarter_of(d: date) -> int:
    return (d.month - 1) // 3 + 1


def resolve(label: str | None, today: date | None = None) -> dict | None:
    """
    Return {"start": ISO, "end": ISO, "label": str} or None if not recognised.

    Indian financial year (Apr–Mar) is used for "financial year"/"FY" phrasing;
    plain "this year" is calendar year-to-date. This distinction is surfaced to
    the user as an assumption by the caller.
    """
    if not label:
        return None
    today = today or date.today()
    t = label.strip().lower()

    def out(start: date, end: date, lbl: str) -> dict:
        return {"start": start.isoformat(), "end": end.isoformat(), "label": lbl}

    q = _quarter_of(today)
    y = today.year

    if t in {"this quarter", "current quarter"}:
        s = _quarter_start(y, q)
        e = date(y, s.month + 2, 1)
        # end of that month
        nxt = date(e.year + (e.month // 12), (e.month % 12) + 1, 1)
        return out(s, _prev_day(nxt), f"Q{q} {y}")
    if t in {"last quarter", "previous quarter"}:
        pq, py = (q - 1, y) if q > 1 else (4, y - 1)
        s = _quarter_start(py, pq)
        e_month_first = date(py, s.month + 2, 1)
        nxt = date(e_month_first.year + (e_month_first.month // 12),
                   (e_month_first.month % 12) + 1, 1)
        return out(s, _prev_day(nxt), f"Q{pq} {py}")
    if t in {"this month", "current month"}:
        s = date(y, today.month, 1)
        nxt = date(y + (today.month // 12), (today.month % 12) + 1, 1)
        return out(s, _prev_day(nxt), s.strftime("%B %Y"))
    if t in {"last month", "previous month"}:
        first = date(y, today.month, 1)
        end = _prev_day(first)
        s = date(end.year, end.month, 1)
        return out(s, end, s.strftime("%B %Y"))
    if t in {"this year", "current year", "ytd", "year to date"}:
        return out(date(y, 1, 1), today, f"{y} (YTD)")
    if t in {"this financial year", "fy", "financial year", "this fy"}:
        # Indian FY: Apr 1 -> Mar 31
        fy_start_year = y if today.month >= 4 else y - 1
        return out(date(fy_start_year, 4, 1), date(fy_start_year + 1, 3, 31),
                   f"FY{fy_start_year % 100}-{(fy_start_year + 1) % 100}")
    # Bare 4-digit year
    if t.isdigit() and len(t) == 4:
        yy = int(t)
        return out(date(yy, 1, 1), date(yy, 12, 31), t)
    return None


def _prev_day(d: date) -> date:
    from datetime import timedelta
    return d - timedelta(days=1)
