"""
FastAPI application: JSON API + static frontend in one deployable unit.

Serving the frontend from the same origin as the API keeps the deployment
surface tiny (one Render service, no CORS dance) — a deliberate trade-off
documented in DECISION_LOG.md.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, bi_engine, llm
from .config import FRONTEND_DIR, board_config_present, settings
from .datasource import get_dataset
from .monday_client import MondayError

logger = logging.getLogger("skylark")

app = FastAPI(
    title="Skylark BI Agent",
    version="1.0.0",
    description="Conversational business intelligence over monday.com deals & work orders.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# Safe, user-facing message when the data source is down (details go to logs).
DATA_UNAVAILABLE = "Live business data is temporarily unavailable. Please try again shortly."


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Never leak stack traces or internals to the client."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"error": "Something went wrong on our side."}, status_code=500)


class ChatRequest(BaseModel):
    question: str = Field(min_length=0, max_length=1000)


EXAMPLE_QUESTIONS = [
    "How's our pipeline looking in the energy sector?",
    "What's our total billed revenue and how much have we collected?",
    "What's our win rate in mining?",
    "Which sectors are performing best?",
    "How much is outstanding in receivables?",
    "Give me a leadership update.",
    "What data-quality issues should I know about?",
]


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "monday_configured": settings.monday_configured,
        "llm_enabled": settings.llm_enabled,
        "llm_provider": llm.provider_label(),
        "board_config_present": board_config_present(),
    }


@app.get("/api/examples")
def examples() -> dict:
    return {"examples": EXAMPLE_QUESTIONS}


@app.post("/api/chat")
def chat(req: ChatRequest) -> JSONResponse:
    result = agent.answer(req.question)
    status = 200 if result["type"] != "error" else 503
    return JSONResponse(result, status_code=status)


@app.get("/api/overview")
def overview() -> JSONResponse:
    """Compact dashboard payload for the frontend landing view."""
    try:
        ds = get_dataset()
    except MondayError as exc:
        logger.warning("overview: data source unavailable: %s", exc)
        return JSONResponse({"error": DATA_UNAVAILABLE}, status_code=503)
    pipeline = bi_engine.pipeline_health(ds)
    revenue = bi_engine.revenue_summary(ds)
    sectors = bi_engine.sector_performance(ds)
    return JSONResponse({
        "pipeline": pipeline.summary_values,
        "revenue": revenue.summary_values,
        "sectors": sectors.breakdown,
        "quality": {
            "deals": ds.deals_quality.to_dict(),
            "work_orders": ds.wo_quality.to_dict(),
        },
        "data_source": {
            "source": ds.source,
            "monday_account": ds.account,
            "deals_count": int(ds.deals.shape[0]),
            "work_orders_count": int(ds.work_orders.shape[0]),
        },
    })


@app.get("/api/dashboard")
def dashboard(refresh: bool = False) -> JSONResponse:
    """
    Structured payload powering the BI workspace views (Overview / Sales /
    Operations / Financials). Composes existing deterministic metrics — no new
    business logic. Deliberately omits the monday account email from the UI.
    """
    try:
        ds = get_dataset(force_refresh=refresh)
    except MondayError as exc:
        logger.warning("dashboard: data source unavailable: %s", exc)
        return JSONResponse({"error": DATA_UNAVAILABLE}, status_code=503)

    pipeline = bi_engine.pipeline_health(ds)
    revenue = bi_engine.revenue_summary(ds)
    collections = bi_engine.collections_summary(ds)
    win = bi_engine.win_rate(ds)
    sectors = bi_engine.sector_performance(ds)
    stages = bi_engine.stage_breakdown(ds)
    statuses = bi_engine.deal_status_breakdown(ds)
    operations = bi_engine.operations_summary(ds)

    live = ds.source == "monday"
    return JSONResponse({
        "data_source": {
            "source": "Monday.com",
            "live": live,
            "label": "Monday.com · Live data" if live else "Monday.com · Cached data",
            "deals_count": int(ds.deals.shape[0]),
            "work_orders_count": int(ds.work_orders.shape[0]),
            "last_refreshed": datetime.now(timezone.utc).isoformat(),
        },
        "pipeline": {"values": pipeline.summary_values, "caveats": pipeline.caveats,
                     "audit": pipeline.audit},
        "revenue": {"values": revenue.summary_values, "caveats": revenue.caveats,
                    "audit": revenue.audit},
        "collections": {"values": collections.summary_values, "caveats": collections.caveats},
        "win_rate": {"values": win.summary_values},
        "sectors": sectors.breakdown,
        "stages": stages.breakdown,
        "statuses": statuses.breakdown,
        "operations": {"values": operations.summary_values,
                       "breakdown": operations.breakdown, "caveats": operations.caveats},
        "quality": {
            "deals": ds.deals_quality.to_dict(),
            "work_orders": ds.wo_quality.to_dict(),
        },
    })


@app.get("/api/quality")
def quality() -> JSONResponse:
    try:
        ds = get_dataset()
    except MondayError as exc:
        logger.warning("quality: data source unavailable: %s", exc)
        return JSONResponse({"error": DATA_UNAVAILABLE}, status_code=503)
    return JSONResponse(bi_engine.data_quality(ds).to_dict())


# --- Static frontend -------------------------------------------------------
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(str(FRONTEND_DIR / "index.html"))
