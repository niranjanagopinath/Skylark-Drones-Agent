"""
Logical schema for the two boards.

This is the app-side contract: it names the logical fields the BI engine relies
on, groups them by semantic type (money / date / category), and defines the
*small, documented* set of category normalizations we apply. monday's opaque
column ids are mapped to these logical names via board_config.json at load time.

Keeping this separate from board_config.json means the BI logic is written
against stable names ("deal_value"), not against monday ids ("numeric_mm6qae92").
"""

from __future__ import annotations

# --- Deals ------------------------------------------------------------------
DEALS_MONEY = ["deal_value"]
DEALS_DATES = ["close_date", "tentative_close_date", "created_date"]
DEALS_CATEGORICAL = ["deal_status", "deal_stage", "closure_probability", "sector"]
DEALS_TEXT = ["owner", "client_code", "product", "source_row"]

# --- Work Orders ------------------------------------------------------------
WO_MONEY = [
    "order_value",
    "billed_value",
    "collected_amount",
    "amount_to_be_billed",
    "amount_receivable",
]
WO_DATES = ["date_po_loi", "start_date", "end_date"]
WO_CATEGORICAL = ["nature_of_work", "execution_status", "sector"]
WO_TEXT = [
    "customer_code",
    "serial",
    "document_type",
    "owner",
    "type_of_work",
    "software_platform",
    "invoice_status",
    "source_row",
]

# ---------------------------------------------------------------------------
# Category normalization.
#
# We ONLY fix whitespace/case and strip out "header echo" artifacts. We do NOT
# merge distinct business categories (e.g. we never fold "DSP" into "Others") —
# that would be an unaudited business assumption. Any real merging a user asks
# for is handled at query time and disclosed.
# ---------------------------------------------------------------------------

# Values that are spreadsheet header text leaking into data — treat as missing.
HEADER_ECHO_TOKENS = {
    "sector/service",
    "deal stage",
    "deal status",
    "closure probability",
    "close date (a)",
    "masked deal value",
    "tentative close date",
    "created date",
    "nature of work",
    "execution status",
}

# Canonical deal statuses we recognise. Anything else is kept verbatim but
# flagged as "other" so counts stay honest.
CANONICAL_DEAL_STATUS = {"Won", "Dead", "Open", "On Hold"}

# Sector labels present in the boards (used to guide intent parsing and to
# canonicalise casing). If a user names something outside this set, we keep their
# term so the BI engine can report "unknown sector" instead of silently answering
# with all-company data mislabelled as that sector.
KNOWN_SECTORS = [
    "Mining", "Renewables", "Railways", "Powerline", "Construction",
    "DSP", "Others", "Aviation", "Manufacturing",
    "Security and Surveillance", "Tender",
]

# Sector query aliases: how a founder's word maps to a sector label present in
# the data. Applied ONLY to interpret questions (never to rewrite the data), and
# always disclosed in the answer. "Energy" is the classic example — the dataset
# has no "Energy" sector; renewables is its closest real proxy.
SECTOR_QUERY_ALIASES = {
    "energy": "Renewables",
    "renewable": "Renewables",
    "renewables": "Renewables",
    "solar": "Renewables",
    "wind": "Renewables",
    "mining": "Mining",
    "railway": "Railways",
    "railways": "Railways",
    "powerline": "Powerline",
    "power line": "Powerline",
    "transmission": "Powerline",
    "construction": "Construction",
    "infra": "Construction",
    "infrastructure": "Construction",
}

# Deal stages that mean "the deal is still live in the funnel" vs terminal.
# Terminal-lost stages/statuses are excluded from "open pipeline".
TERMINAL_LOST_STATUS = {"Dead"}
TERMINAL_WON_STATUS = {"Won"}
