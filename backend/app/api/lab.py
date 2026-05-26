from __future__ import annotations

import hashlib
import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from app.adapters.firecrawl_client import FirecrawlError
from app.adapters.serpapi_client import SerpapiError
from app.models.schemas import (
    ResearchPreviewResponse,
    ResearchRequest,
    RunContinueRequest,
    RunListResponse,
    RunRequest,
    RunResult,
    StepConfig,
)
from app.observability.run_usage import run_tracking
from app.reports.cost import build_cost_report, build_runtime_report
from app.repositories.research_session import create_research_session
from app.repositories.run_history import RunSaveMetadata, delete_run, get_run, list_runs, save_run
from app.workflow.orchestrator import execute_llm_steps, execute_research, execute_run_continue, execute_run_safe

router = APIRouter()
logger = logging.getLogger(__name__)


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _persist_run(
    result: RunResult,
    *,
    manufacturer_name: str,
    manufacturer_product_number: str,
    style_guide_filename: str = "",
    style_guide_hash: str | None = None,
) -> None:
    try:
        save_run(
            result,
            RunSaveMetadata(
                manufacturer_name=manufacturer_name,
                manufacturer_product_number=manufacturer_product_number,
                style_guide_filename=style_guide_filename,
                style_guide_hash=style_guide_hash,
            ),
        )
    except Exception:
        logger.exception("Run history save failed")


def _research_audit(research) -> dict:
    return {
        "manufacturer_data_available": research.manufacturer_data_available,
        "fallback_ecommerce_used": research.fallback_ecommerce_used,
        "normalized_manufacturer": research.normalized_manufacturer,
        "normalized_mpn": research.normalized_mpn,
        "product_family_hint": research.product_family_hint,
        "research_tier": research.research_tier,
        "research_tier_reason": research.research_tier_reason,
    }


@router.post("/research", response_model=ResearchPreviewResponse)
async def research_lab(payload: ResearchRequest) -> ResearchPreviewResponse:
    try:
        with run_tracking() as (collector, timer):
            timer.start_phase("match_and_research")
            research = await execute_research(
                manufacturer_name=payload.manufacturer_name,
                manufacturer_product_number=payload.manufacturer_product_number,
                product_family_hint=payload.product_family_hint,
            )
            timer.end_phase()
            cost_lines, total_cost = build_cost_report(collector)
            runtime_lines, total_runtime = build_runtime_report(timer)
    except (SerpapiError, FirecrawlError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    session_id = create_research_session(research)
    source_records = [s.record for s in research.sources]
    audit = _research_audit(research)

    return ResearchPreviewResponse(
        research_session_id=session_id,
        status="ready" if research.match_verified else "incomplete",
        research_tier=research.research_tier,
        research_tier_reason=research.research_tier_reason,
        match_verified=research.match_verified,
        incomplete_reason=research.incomplete_reason,
        manufacturer_name=research.normalized_manufacturer,
        manufacturer_product_number=research.normalized_mpn,
        product_family_hint=research.product_family_hint,
        sources=source_records,
        evidence_text=research.evidence_text,
        cost_lines=cost_lines,
        total_cost_usd=total_cost,
        runtime_lines=runtime_lines,
        total_runtime_ms=total_runtime,
        audit=audit,
    )


@router.post("/run/continue", response_model=RunResult)
async def continue_lab(payload: RunContinueRequest) -> RunResult:
    result = await execute_run_continue(payload)
    style_hash = None
    if payload.style_guide_text:
        style_hash = _hash_bytes(payload.style_guide_text.encode("utf-8"))
    _persist_run(
        result,
        manufacturer_name=str(result.audit.get("normalized_manufacturer", "")),
        manufacturer_product_number=str(result.audit.get("normalized_mpn", "")),
        style_guide_filename=payload.style_guide_filename,
        style_guide_hash=style_hash,
    )
    return result


@router.post("/run", response_model=RunResult)
async def run_lab(payload: RunRequest) -> RunResult:
    result = await execute_run_safe(payload)
    style_hash = None
    if payload.style_guide_text:
        style_hash = _hash_bytes(payload.style_guide_text.encode("utf-8"))
    _persist_run(
        result,
        manufacturer_name=payload.manufacturer_name,
        manufacturer_product_number=payload.manufacturer_product_number,
        style_guide_filename=payload.style_guide_filename,
        style_guide_hash=style_hash,
    )
    return result


@router.post("/run-with-upload", response_model=RunResult)
async def run_lab_with_upload(
    manufacturer_name: str = Form(...),
    manufacturer_product_number: str = Form(...),
    product_family_hint: str = Form(""),
    step1_name: str = Form(...),
    step1_prompt: str = Form(...),
    step1_model: str = Form(...),
    step2_name: str = Form(...),
    step2_prompt: str = Form(...),
    step2_model: str = Form(...),
    step3_name: str = Form(...),
    step3_prompt: str = Form(...),
    step3_model: str = Form(...),
    style_guide: UploadFile | None = File(default=None),
) -> RunResult:
    style_guide_text = ""
    style_guide_filename = ""
    style_guide_hash: str | None = None
    if style_guide is not None and style_guide.filename:
        raw = await style_guide.read()
        style_guide_hash = _hash_bytes(raw)
        try:
            style_guide_text = raw.decode("utf-8")
        except UnicodeDecodeError:
            style_guide_text = raw.decode("latin-1", errors="replace")
        style_guide_filename = style_guide.filename or "style-guide.txt"

    payload = RunRequest(
        manufacturer_name=manufacturer_name,
        manufacturer_product_number=manufacturer_product_number,
        product_family_hint=product_family_hint,
        style_guide_text=style_guide_text,
        style_guide_filename=style_guide_filename,
        step1=StepConfig(name=step1_name, prompt=step1_prompt, model=step1_model),
        step2=StepConfig(name=step2_name, prompt=step2_prompt, model=step2_model),
        step3=StepConfig(name=step3_name, prompt=step3_prompt, model=step3_model),
    )
    result = await execute_run_safe(payload)
    _persist_run(
        result,
        manufacturer_name=manufacturer_name,
        manufacturer_product_number=manufacturer_product_number,
        style_guide_filename=style_guide_filename,
        style_guide_hash=style_guide_hash,
    )
    return result


@router.get("/runs", response_model=RunListResponse)
def get_runs(limit: int = 50, offset: int = 0) -> RunListResponse:
    return list_runs(limit=limit, offset=offset)


@router.get("/runs/{run_id}", response_model=RunResult)
def get_run_by_id(run_id: int) -> RunResult:
    result = get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return result


@router.delete("/runs/{run_id}", status_code=204)
def remove_run(run_id: int) -> None:
    if not delete_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found.")


@router.post("/report/download")
async def download_report(payload: RunResult) -> HTMLResponse:
    html = payload.internal_report_html or "<html><body><p>No report available.</p></body></html>"
    return HTMLResponse(content=html, headers={"Content-Disposition": 'attachment; filename="lab-report.html"'})
