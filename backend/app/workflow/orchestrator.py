from __future__ import annotations

import logging
import re
import time

from sqlmodel import Session, select

from app.adapters.firecrawl_client import FirecrawlError
from app.adapters.serpapi_client import SerpapiError
from app.config import get_settings
from app.models.db import ModelCatalogEntry, get_engine
from app.models.schemas import RunRequest, RunResult
from app.observability.run_usage import llm_step_context, run_tracking
from app.reports.cost import build_cost_report, build_runtime_report
from app.reports.internal import render_internal_report
from app.research.searcher import research_product
from app.workflow.llm_router import complete_text, provider_for_model
from app.workflow.prompt_compact import style_guide_for_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an internal AI assistant for product detail page content generation testing. "
    "Follow the style guide as a hard rulebook. Use only validated source evidence. "
    "Never invent unsupported product facts."
)

_MIN_FINAL_CONTENT_CHARS = 80


def _output_is_insufficient(content: str, manufacturer: str, mpn: str) -> bool:
    stripped = content.strip()
    if len(stripped) < _MIN_FINAL_CONTENT_CHARS:
        return True
    compact = re.sub(r"\s+", " ", stripped.lower())
    for candidate in {
        manufacturer.lower().strip(),
        mpn.lower().strip(),
        f"{manufacturer} {mpn}".lower().strip(),
        f"{manufacturer} ({mpn})".lower().strip(),
    }:
        if candidate and compact == candidate:
            return True
    return False


def _model_provider(model_id: str) -> str:
    with Session(get_engine()) as session:
        row = session.exec(select(ModelCatalogEntry).where(ModelCatalogEntry.model_id == model_id)).first()
    return provider_for_model(model_id, provider_hint=row.provider if row else None)


async def execute_run(payload: RunRequest) -> RunResult:
    settings = get_settings()
    deadline = time.monotonic() + settings.max_run_seconds
    raw_style = payload.style_guide_text or ""
    style_guide = style_guide_for_llm(raw_style)
    style_guide_truncated = bool(raw_style) and len(raw_style) > len(style_guide)

    with run_tracking() as (collector, timer):
        timer.start_phase("match_and_research")
        try:
            research = await research_product(
                manufacturer=payload.manufacturer_name,
                mpn=payload.manufacturer_product_number,
            )
        except (SerpapiError, FirecrawlError) as exc:
            timer.end_phase()
            return _incomplete(
                str(exc),
                [],
                collector,
                timer,
                payload,
                style_guide_truncated,
                {"research_error": str(exc)},
            )
        except Exception as exc:
            logger.exception("Research phase failed")
            timer.end_phase()
            return _incomplete(
                f"Model or API error prevented completion: {exc}",
                [],
                collector,
                timer,
                payload,
                style_guide_truncated,
                {"research_error": str(exc)},
            )
        timer.end_phase()

        source_records = [s.record for s in research.sources]
        audit = {
            "manufacturer_data_available": research.manufacturer_data_available,
            "fallback_ecommerce_used": research.fallback_ecommerce_used,
            "style_guide_truncated": style_guide_truncated,
            "style_guide_provided": bool(style_guide.strip()),
            "normalized_manufacturer": research.normalized_manufacturer,
            "normalized_mpn": research.normalized_mpn,
        }

        manufacturer = research.normalized_manufacturer
        mpn = research.normalized_mpn

        style_guide_block = (
            f"STYLE GUIDE (hard rulebook):\n{style_guide}\n\n"
            if style_guide.strip()
            else "STYLE GUIDE: (none provided — use clear, professional PDP structure.)\n\n"
        )

        context_header = (
            f"Manufacturer: {manufacturer}\n"
            f"Manufacturer product number: {mpn}\n\n"
            f"{style_guide_block}"
            f"VALIDATED SOURCE EVIDENCE:\n{research.evidence_text}\n"
        )

        if time.monotonic() > deadline:
            return _incomplete(
                "Run exceeded 180s maximum runtime.",
                source_records,
                collector,
                timer,
                payload,
                style_guide_truncated,
                audit,
            )

        if not research.match_verified:
            return _incomplete(
                research.incomplete_reason or "Exact product match could not be verified.",
                source_records,
                collector,
                timer,
                payload,
                style_guide_truncated,
                audit,
            )

        step_outputs: dict[int, str] = {}
        steps = [
            (1, payload.step1),
            (2, payload.step2),
            (3, payload.step3),
        ]

        for step_no, step in steps:
            if time.monotonic() > deadline:
                return _incomplete(
                    "Run exceeded 180s maximum runtime.",
                    source_records,
                    collector,
                    timer,
                    payload,
                    style_guide_truncated,
                    audit,
                    step_outputs.get(1),
                    step_outputs.get(2),
                )

            prior = ""
            if step_no == 2 and 1 in step_outputs:
                prior = f"\n\nSTEP 1 OUTPUT:\n{step_outputs[1]}\n"
            if step_no == 3:
                parts = []
                if 1 in step_outputs:
                    parts.append(f"STEP 1 OUTPUT:\n{step_outputs[1]}")
                if 2 in step_outputs:
                    parts.append(f"STEP 2 OUTPUT:\n{step_outputs[2]}")
                prior = "\n\n".join(parts)
                if prior:
                    prior = f"\n\n{prior}\n"

            user_prompt = f"{step.prompt.strip()}\n\n{context_header}{prior}"
            provider = _model_provider(step.model)

            with llm_step_context(step_no=step_no, step_name=step.name):
                try:
                    output = await complete_text(
                        model=step.model,
                        provider=provider,
                        system=SYSTEM_PROMPT,
                        user=user_prompt,
                    )
                except Exception as exc:
                    logger.exception("Model step failed")
                    return _incomplete(
                        f"Model or API error prevented completion: {exc}",
                        source_records,
                        collector,
                        timer,
                        payload,
                        style_guide_truncated,
                        audit,
                        step_outputs.get(1),
                        step_outputs.get(2),
                    )
            step_outputs[step_no] = output

        cost_lines, total_cost = build_cost_report(collector)
        runtime_lines, total_runtime = build_runtime_report(timer)
        final_content = step_outputs.get(3, "").strip()

        if _output_is_insufficient(final_content, manufacturer, mpn):
            return _incomplete(
                "Source evidence was insufficient to satisfy the required prompt output safely.",
                source_records,
                collector,
                timer,
                payload,
                style_guide_truncated,
                audit,
                step_outputs.get(1),
                step_outputs.get(2),
            )

        steps_config = [
            {"name": payload.step1.name, "model": payload.step1.model, "prompt": payload.step1.prompt},
            {"name": payload.step2.name, "model": payload.step2.model, "prompt": payload.step2.prompt},
            {"name": payload.step3.name, "model": payload.step3.model, "prompt": payload.step3.prompt},
        ]
        report_html = render_internal_report(
            manufacturer=manufacturer,
            mpn=mpn,
            style_guide_filename=payload.style_guide_filename,
            style_guide_truncated=style_guide_truncated,
            steps=steps_config,
            sources=[s.model_dump() for s in source_records],
            match_verified=True,
            incomplete_reason=None,
            cost_lines=[c.model_dump() for c in cost_lines],
            total_cost_usd=total_cost,
            runtime_lines=[r.model_dump() for r in runtime_lines],
            total_runtime_ms=total_runtime,
            step1_output=step_outputs.get(1),
            step2_output=step_outputs.get(2),
            final_content=final_content,
            audit=audit,
        )

        return RunResult(
            status="complete",
            final_content=final_content,
            style_guide_truncated=style_guide_truncated,
            match_verified=True,
            sources=source_records,
            cost_lines=cost_lines,
            total_cost_usd=total_cost,
            runtime_lines=runtime_lines,
            total_runtime_ms=total_runtime,
            step1_output=step_outputs.get(1),
            step2_output=step_outputs.get(2),
            internal_report_html=report_html,
            audit=audit,
        )


def _incomplete(
    reason: str,
    sources,
    collector,
    timer,
    payload: RunRequest,
    style_guide_truncated: bool,
    audit: dict,
    step1_output: str | None = None,
    step2_output: str | None = None,
) -> RunResult:
    cost_lines, total_cost = build_cost_report(collector)
    runtime_lines, total_runtime = build_runtime_report(timer)
    steps_config = [
        {"name": payload.step1.name, "model": payload.step1.model, "prompt": payload.step1.prompt},
        {"name": payload.step2.name, "model": payload.step2.model, "prompt": payload.step2.prompt},
        {"name": payload.step3.name, "model": payload.step3.model, "prompt": payload.step3.prompt},
    ]
    report_html = render_internal_report(
        manufacturer=payload.manufacturer_name,
        mpn=payload.manufacturer_product_number,
        style_guide_filename=payload.style_guide_filename,
        style_guide_truncated=style_guide_truncated,
        steps=steps_config,
        sources=[s.model_dump() for s in sources],
        match_verified=False,
        incomplete_reason=reason,
        cost_lines=[c.model_dump() for c in cost_lines],
        total_cost_usd=total_cost,
        runtime_lines=[r.model_dump() for r in runtime_lines],
        total_runtime_ms=total_runtime,
        step1_output=step1_output,
        step2_output=step2_output,
        final_content=None,
        audit=audit,
    )
    return RunResult(
        status="incomplete",
        incomplete_reason=f"Incomplete: {reason}",
        style_guide_truncated=style_guide_truncated,
        match_verified=False,
        sources=sources,
        cost_lines=cost_lines,
        total_cost_usd=total_cost,
        runtime_lines=runtime_lines,
        total_runtime_ms=total_runtime,
        step1_output=step1_output,
        step2_output=step2_output,
        internal_report_html=report_html,
        audit=audit,
    )


async def execute_run_safe(payload: RunRequest) -> RunResult:
    return await execute_run(payload)
