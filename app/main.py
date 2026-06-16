"""FastAPI entrypoint.

Exposes:
  GET  /health             - liveness + chunk count
  POST /ask                - grounded Q&A over the guidelines
  POST /analyze-encounter  - documentation-vs-code analysis
  POST /admin/ingest       - run ingestion (guarded by ADMIN_TOKEN header)
  GET  /                   - basic frontend
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import db
from .config import get_settings
from .schemas import AskRequest, AskResponse, EncounterAnalysisResponse, EncounterRequest
from .services import ask_service, encounter_service

_settings = get_settings()
app = FastAPI(title="Medical Necessity Assistant", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")


@app.get("/health")
def health():
    try:
        n = db.count_chunks()
        return {"status": "ok", "chunks_indexed": n}
    except Exception as exc:  # noqa: BLE001
        return {"status": "degraded", "detail": str(exc)}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    return ask_service.answer_question(req.question)


@app.post("/analyze-encounter", response_model=EncounterAnalysisResponse)
def analyze_encounter(req: EncounterRequest):
    return encounter_service.analyze(req)


@app.post("/admin/ingest")
def admin_ingest(x_admin_token: str = Header(default="")):
    if x_admin_token != _settings.admin_token:
        raise HTTPException(status_code=401, detail="invalid admin token")
    from .ingestion import run_ingestion
    return run_ingestion()


@app.get("/")
def index():
    if os.path.exists(_FRONTEND):
        return FileResponse(_FRONTEND)
    return {"status": "ok", "hint": "frontend not found; use /docs"}
