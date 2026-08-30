"""
One-time ETL: Excel  ->  monday.com boards.

WHY THIS EXISTS
---------------
The assignment ships two messy Excel files and asks us to import them into
monday.com as two boards, then have the agent query monday *dynamically* at
runtime. This script is that import step. It is NOT part of the request path —
the running app never reads Excel; it only reads monday.

DESIGN NOTES
------------
* We deliberately preserve real-world messiness in monday (missing values,
  duplicate deals, negative amounts, inconsistent categories). Cleaning happens
  at query time in the app's normalization layer, where it is unit-tested and
  visible to the user as data-quality caveats. monday is the *raw* source.
* The ONE thing we drop here are "header echo" rows — spreadsheet artifacts where
  a header row was pasted into the data (e.g. a row whose cells literally read
  "Deal Stage", "Sector/service"). These are not business records at all.
* Numeric cells are coerced to numbers (missing stays missing — never 0).
  Date serials are converted to ISO. Everything else is preserved verbatim.
* The board + column IDs monday assigns are written to
  backend/app/board_config.json, which is the single source the app uses to map
  monday's opaque column ids to our logical field names. Nothing is hardcoded.

USAGE
-----
    MONDAY_API_TOKEN=... python scripts/ingest_to_monday.py
or put the token in backend/.env and just run:
    python scripts/ingest_to_monday.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from excel_reader import excel_serial_to_iso, parse_number, read_sheet  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")

MONDAY_URL = os.getenv("MONDAY_API_URL", "https://api.monday.com/v2")
TOKEN = os.getenv("MONDAY_API_TOKEN", "").strip()
BOARD_CONFIG_PATH = ROOT / "backend" / "app" / "board_config.json"

DEALS_XLSX = ROOT / "data" / "Deal_funnel_Data.xlsx"
WO_XLSX = ROOT / "data" / "Work_Order_Tracker_Data.xlsx"

# ---------------------------------------------------------------------------
# Board schemas: (logical_name, excel_column, monday_type, board_title)
# `source_row` has no excel column — we synthesize it for auditability.
# ---------------------------------------------------------------------------
NAME_COL_DEALS = "A"
DEALS_SPEC = [
    ("owner", "B", "text", "Owner"),
    ("client_code", "C", "text", "Client Code"),
    ("deal_status", "D", "status", "Deal Status"),
    ("close_date", "E", "date", "Close Date"),
    ("closure_probability", "F", "status", "Closure Probability"),
    ("deal_value", "G", "numbers", "Deal Value"),
    ("tentative_close_date", "H", "date", "Tentative Close Date"),
    ("deal_stage", "I", "status", "Deal Stage"),
    ("product", "J", "text", "Product"),
    ("sector", "K", "status", "Sector"),
    ("created_date", "L", "date", "Created Date"),
    ("source_row", None, "text", "Source Row"),
]

NAME_COL_WO = "A"
WO_SPEC = [
    ("customer_code", "B", "text", "Customer Code"),
    ("serial", "C", "text", "Serial"),
    ("nature_of_work", "D", "status", "Nature of Work"),
    ("execution_status", "F", "status", "Execution Status"),
    ("date_po_loi", "H", "date", "Date of PO/LOI"),
    ("document_type", "I", "text", "Document Type"),
    ("start_date", "J", "date", "Start Date"),
    ("end_date", "K", "date", "End Date"),
    ("owner", "L", "text", "Owner"),
    ("sector", "M", "status", "Sector"),
    ("type_of_work", "N", "text", "Type of Work"),
    ("software_platform", "O", "text", "Software Platform"),
    ("order_value", "S", "numbers", "Order Value (Incl GST)"),
    ("billed_value", "U", "numbers", "Billed Value (Incl GST)"),
    ("collected_amount", "V", "numbers", "Collected Amount (Incl GST)"),
    ("amount_to_be_billed", "X", "numbers", "Amount To Be Billed (Incl GST)"),
    ("amount_receivable", "Y", "numbers", "Amount Receivable"),
    ("invoice_status", "AE", "text", "Invoice Status"),
    ("source_row", None, "text", "Source Row"),
]

BATCH = 12  # items per GraphQL request (keeps complexity within monday limits)


# ---------------------------------------------------------------------------
# monday HTTP helper with retry/backoff on rate/complexity limits.
# ---------------------------------------------------------------------------
def monday(query: str, variables: dict | None = None, *, retries: int = 6) -> dict:
    headers = {"Authorization": TOKEN, "Content-Type": "application/json",
               "API-Version": "2024-10"}
    payload = {"query": query, "variables": variables or {}}
    delay = 2.0
    for attempt in range(retries):
        resp = httpx.post(MONDAY_URL, json=payload, headers=headers, timeout=60)
        try:
            body = resp.json()
        except Exception:
            body = {"_raw": resp.text}
        errors = body.get("errors") or body.get("error_message")
        status = body.get("status_code") or resp.status_code
        # monday signals throttling via error_code / 429 / complexity messages.
        throttled = (
            resp.status_code == 429
            or body.get("error_code") in {"ComplexityException", "RATE_LIMIT_EXCEEDED"}
            or (isinstance(errors, list) and any("complexity" in str(e).lower() for e in errors))
        )
        if throttled and attempt < retries - 1:
            print(f"  throttled (attempt {attempt+1}); sleeping {delay:.0f}s")
            time.sleep(delay)
            delay = min(delay * 2, 60)
            continue
        if errors:
            raise RuntimeError(f"monday API error (status {status}): {errors}")
        return body["data"]
    raise RuntimeError("monday API: exhausted retries")


# ---------------------------------------------------------------------------
# Build clean item payloads from an Excel sheet.
# ---------------------------------------------------------------------------
def build_records(rows, name_col, spec):
    header = rows[0]
    header_texts = {c: v for c, v in header.items()}
    data_rows = rows[1:]

    records, dropped_header_echo, blank = [], 0, 0
    for idx, row in enumerate(data_rows, start=1):
        # Drop spreadsheet "header echo" artifacts.
        echo = sum(1 for c, v in row.items() if v and v == header_texts.get(c))
        if echo >= 2:
            dropped_header_echo += 1
            continue
        name = (row.get(name_col) or "").strip()
        # A row with no name and no other meaningful content is noise.
        if not name and not any(v for v in row.values()):
            blank += 1
            continue

        col_values: dict[str, object] = {}
        for logical, excel_col, mtype, _title in spec:
            if logical == "source_row":
                col_values[logical] = str(idx)
                continue
            raw = (row.get(excel_col) or "").strip() if excel_col else ""
            if raw == "":
                continue
            if mtype == "numbers":
                n = parse_number(raw)
                if n is not None:
                    col_values[logical] = n
            elif mtype == "date":
                iso = excel_serial_to_iso(raw)
                if iso is None and raw:
                    # Sometimes already an ISO/parseable string; keep only if it
                    # looks like a date to avoid polluting the date column.
                    iso = raw if raw[:4].isdigit() and "-" in raw else None
                if iso:
                    col_values[logical] = iso
            else:  # text / status
                col_values[logical] = raw
        records.append({"name": name or "(unnamed)", "values": col_values})

    return records, {"dropped_header_echo": dropped_header_echo, "blank_skipped": blank}


# ---------------------------------------------------------------------------
# Board + column creation.
# ---------------------------------------------------------------------------
def create_board(title: str, description: str) -> dict:
    q = """
    mutation ($name: String!, $desc: String) {
      create_board(board_name: $name, board_kind: public, description: $desc) {
        id
        url
      }
    }"""
    data = monday(q, {"name": title, "desc": description})
    return data["create_board"]


def create_column(board_id: str, title: str, ctype: str) -> str:
    q = """
    mutation ($board: ID!, $title: String!, $ctype: ColumnType!) {
      create_column(board_id: $board, title: $title, column_type: $ctype) { id }
    }"""
    data = monday(q, {"board": board_id, "title": title, "ctype": ctype})
    return data["create_column"]["id"]


def clear_default_items(board_id: str) -> int:
    """Remove monday's auto-created empty sample item(s) so counts stay pristine."""
    q = ("query ($b: [ID!]) { boards(ids: $b) { items_page(limit: 50) "
         "{ items { id column_values { text } } } } }")
    items = monday(q, {"b": [board_id]})["boards"][0]["items_page"]["items"]
    removed = 0
    for it in items:
        if not any((cv["text"] or "").strip() for cv in it["column_values"]):
            monday(f'mutation {{ delete_item(item_id: {it["id"]}) {{ id }} }}')
            removed += 1
    return removed


def build_column_map(board_id: str, spec) -> tuple[dict, dict]:
    """Create every non-name column; return {logical: monday_col_id} and meta."""
    col_map = {"name": "name"}
    meta = {"name": {"title": "Name", "type": "name"}}
    for logical, excel_col, mtype, title in spec:
        cid = create_column(board_id, title, mtype)
        col_map[logical] = cid
        meta[logical] = {"title": title, "type": mtype, "excel_col": excel_col}
        print(f"    + column {logical:22} -> {cid} ({mtype})")
        time.sleep(0.3)
    return col_map, meta


def encode_column_values(values: dict, col_map: dict, meta: dict) -> str:
    """Translate logical values into monday's column_values JSON string."""
    out: dict[str, object] = {}
    for logical, val in values.items():
        cid = col_map[logical]
        mtype = meta[logical]["type"]
        if mtype == "numbers":
            out[cid] = str(val)
        elif mtype == "date":
            out[cid] = {"date": val}
        elif mtype == "status":
            out[cid] = {"label": str(val)}
        else:
            out[cid] = str(val)
    return json.dumps(out)


def insert_items(board_id: str, records, col_map, meta) -> int:
    created = 0
    for start in range(0, len(records), BATCH):
        chunk = records[start:start + BATCH]
        var_defs, aliases, variables = ["$board: ID!"], [], {"board": board_id}
        for i, rec in enumerate(chunk):
            var_defs += [f"$n{i}: String!", f"$c{i}: JSON!"]
            aliases.append(
                f'a{i}: create_item(board_id: $board, item_name: $n{i}, '
                f'column_values: $c{i}, create_labels_if_missing: true) {{ id }}'
            )
            variables[f"n{i}"] = rec["name"][:255]
            variables[f"c{i}"] = encode_column_values(rec["values"], col_map, meta)
        query = f"mutation ({', '.join(var_defs)}) {{ {' '.join(aliases)} }}"
        monday(query, variables)
        created += len(chunk)
        print(f"    inserted {created}/{len(records)}")
        time.sleep(0.6)
    return created


def ingest_board(title, desc, xlsx_path, name_col, spec):
    print(f"\n=== {title} ===")
    rows = read_sheet(str(xlsx_path))
    records, stats = build_records(rows, name_col, spec)
    print(f"  parsed {len(records)} records "
          f"(dropped {stats['dropped_header_echo']} header-echo, "
          f"{stats['blank_skipped']} blank)")
    board = create_board(title, desc)
    print(f"  board created: {board['id']}  {board['url']}")
    col_map, meta = build_column_map(board["id"], spec)
    removed = clear_default_items(board["id"])
    if removed:
        print(f"  removed {removed} default sample item(s)")
    inserted = insert_items(board["id"], records, col_map, meta)
    return {
        "board_id": board["id"],
        "board_url": board["url"],
        "columns": col_map,
        "column_meta": meta,
        "records_inserted": inserted,
        "ingest_stats": stats,
    }


def main() -> None:
    if not TOKEN:
        sys.exit("ERROR: MONDAY_API_TOKEN not set (put it in backend/.env).")
    print("Verifying monday token...")
    me = monday("query { me { name email } }")["me"]
    print(f"  authenticated as {me['name']} <{me['email']}>")

    deals = ingest_board(
        "Deals — BI Agent",
        "Sales pipeline data, imported from Deal_funnel_Data.xlsx by ingest_to_monday.py.",
        DEALS_XLSX, NAME_COL_DEALS, DEALS_SPEC,
    )
    work_orders = ingest_board(
        "Work Orders — BI Agent",
        "Project execution & finance data, imported from Work_Order_Tracker_Data.xlsx by ingest_to_monday.py.",
        WO_XLSX, NAME_COL_WO, WO_SPEC,
    )

    config = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "monday_account": f"{me['name']} <{me['email']}>",
        "deals": deals,
        "work_orders": work_orders,
    }
    BOARD_CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"\nWrote {BOARD_CONFIG_PATH.relative_to(ROOT)}")
    print("Done. The app will now read these boards dynamically.")


if __name__ == "__main__":
    main()
