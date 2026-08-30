"""
Dependency-light .xlsx reader used by the ingestion script.

We parse the raw XML inside the .xlsx (openpyxl would also work, but this keeps
the reader transparent and avoids surprises with how a library coerces types).
Every cell is returned as the *string* it renders as in the sheet, plus the raw
type, so the caller decides how to coerce — that decision is business logic and
should be explicit, not hidden inside a parser.
"""

from __future__ import annotations

import html
import re
import zipfile
from datetime import datetime, timedelta

# Excel's epoch. Serial 1 == 1900-01-01, but Excel wrongly treats 1900 as a leap
# year, so the conventional anchor that reproduces real dates is 1899-12-30.
_EXCEL_EPOCH = datetime(1899, 12, 30)


def _col_letters(ref: str) -> str:
    """'B7' -> 'B'."""
    return re.match(r"([A-Z]+)", ref).group(1)


def read_sheet(path: str) -> list[dict[str, str]]:
    """
    Return the first worksheet as a list of {column_letter: value_str} dicts,
    one per row (including the header row as row 0). Empty cells are simply
    absent from a row's dict.
    """
    z = zipfile.ZipFile(path)

    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        sx = z.read("xl/sharedStrings.xml").decode("utf-8", "ignore")
        for si in re.findall(r"<si>(.*?)</si>", sx, re.S):
            texts = re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)
            shared.append(html.unescape("".join(texts)))

    sheet_names = sorted(
        n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n)
    )
    sx = z.read(sheet_names[0]).decode("utf-8", "ignore")

    rows: list[dict[str, str]] = []
    for rm in re.findall(r"<row[^>]*>(.*?)</row>", sx, re.S):
        row: dict[str, str] = {}
        for attrs, body in re.findall(r"<c\b([^>]*)>(.*?)</c>", rm, re.S):
            ref_m = re.search(r'r="([A-Z]+\d+)"', attrs)
            if not ref_m:
                continue
            col = _col_letters(ref_m.group(1))
            type_m = re.search(r't="([^"]+)"', attrs)
            ctype = type_m.group(1) if type_m else None
            v_m = re.search(r"<v>(.*?)</v>", body, re.S)
            val = v_m.group(1) if v_m else ""
            if ctype == "s":  # shared string
                val = shared[int(val)] if val != "" else ""
            elif ctype == "inlineStr":
                its = re.findall(r"<t[^>]*>(.*?)</t>", body, re.S)
                val = html.unescape("".join(its))
            else:
                val = html.unescape(val)
            row[col] = val.strip()
        rows.append(row)
    return rows


def excel_serial_to_iso(value: str) -> str | None:
    """
    Convert an Excel date serial (e.g. '46079') to an ISO date 'YYYY-MM-DD'.
    Returns None if the value is not a plausible serial.
    """
    try:
        serial = float(value)
    except (TypeError, ValueError):
        return None
    # Guard rail: serials in this dataset are ~45000-47000 (years 2023-2028).
    # Anything wildly outside is almost certainly not a date.
    if not (1 <= serial <= 80000):
        return None
    return (_EXCEL_EPOCH + timedelta(days=serial)).date().isoformat()


def parse_number(value: str) -> float | None:
    """
    Coerce a cell to float, tolerating thousands separators and stray spaces.
    Returns None when the cell is not numeric (so 'missing' stays missing —
    we never silently turn text or blanks into 0). Negatives are preserved.
    """
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None
