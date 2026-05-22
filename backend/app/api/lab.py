from __future__ import annotations

from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import HTMLResponse

from app.models.schemas import RunRequest, RunResult, StepConfig
from app.workflow.orchestrator import execute_run_safe

router = APIRouter()


@router.post("/run", response_model=RunResult)
async def run_lab(payload: RunRequest) -> RunResult:
    return await execute_run_safe(payload)


@router.post("/run-with-upload", response_model=RunResult)
async def run_lab_with_upload(
    manufacturer_name: str = Form(...),
    manufacturer_product_number: str = Form(...),
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
    if style_guide is not None and style_guide.filename:
        raw = await style_guide.read()
        try:
            style_guide_text = raw.decode("utf-8")
        except UnicodeDecodeError:
            style_guide_text = raw.decode("latin-1", errors="replace")
        style_guide_filename = style_guide.filename or "style-guide.txt"

    payload = RunRequest(
        manufacturer_name=manufacturer_name,
        manufacturer_product_number=manufacturer_product_number,
        style_guide_text=style_guide_text,
        style_guide_filename=style_guide_filename,
        step1=StepConfig(name=step1_name, prompt=step1_prompt, model=step1_model),
        step2=StepConfig(name=step2_name, prompt=step2_prompt, model=step2_model),
        step3=StepConfig(name=step3_name, prompt=step3_prompt, model=step3_model),
    )
    return await execute_run_safe(payload)


@router.post("/report/download")
async def download_report(payload: RunResult) -> HTMLResponse:
    html = payload.internal_report_html or "<html><body><p>No report available.</p></body></html>"
    return HTMLResponse(content=html, headers={"Content-Disposition": 'attachment; filename="lab-report.html"'})
