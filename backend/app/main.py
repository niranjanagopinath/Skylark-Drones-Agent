"""
FastAPI application: JSON API + static frontend in one deployable unit.

Serving the frontend from the same origin as the API keeps the deployment
surface tiny (one Render service, no CORS dance) — a deliberate trade-off
documented in DECISION_LOG.md.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent, bi_engine, llm
from .config import FRONTEND_DIR, board_config_present, settings
from .datasource import get_dataset
from .monday_client import MondayError

app = FastAPI(
    title="Skylark BI Agent",
    version="1.0.0",
    description="Conversational business intelligence over monday.com deals & work orders.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str


EXAMPLE_QUESTIONS = [
    "How's our pipeline looking for the energy sector this quarter?",
    "What's our total billed revenue and how much have we collected?",
    "What's our win rate in mining?",
    "Compare performance across sectors.",
    "How much is outstanding in receivables?",
    "Give me a leadership update.",
    "What are the data-quality issues I should know about?",
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
        return JSONResponse(
            {"error": str(exc), "hint": "Run scripts/ingest_to_monday.py and set MONDAY_API_TOKEN."},
            status_code=503,
        )
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


@app.get("/api/quality")
def quality() -> JSONResponse:
    try:
        ds = get_dataset()
    except MondayError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    return JSONResponse(bi_engine.data_quality(ds).to_dict())


# --- Static frontend -------------------------------------------------------
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(str(FRONTEND_DIR / "index.html"))
