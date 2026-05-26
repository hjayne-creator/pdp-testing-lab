from __future__ import annotations

import logging
import re
import time

from sqlmodel import Session, select

from app.adapters.firecrawl_client import FirecrawlError
from app.adapters.serpapi_client import SerpapiError
from app.config import get_settings
from app.models.db import ModelCatalogEntry, get_engine
from app.models.schemas import RunContinueRequest, RunRequest, RunResult
from app.observability.run_usage import llm_step_context, run_tracking
from app.reports.cost import build_cost_report, build_runtime_report
from app.reports.internal import render_internal_report
from app.repositories.research_session import delete_research_session, get_research_session
from app.research.searcher import ResearchBundle, research_product
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


def _research_audit(research: ResearchBundle, *, style_guide_truncated: bool, style_guide_provided: bool) -> dict:
    return {
        "manufacturer_data_available": research.manufacturer_data_available,
        "fallback_ecommerce_used": research.fallback_ecommerce_used,
        "style_guide_truncated": style_guide_truncated,
        "style_guide_provided": style_guide_provided,
        "normalized_manufacturer": research.normalized_manufacturer,
        "normalized_mpn": research.normalized_mpn,
        "product_family_hint": research.product_family_hint,
        "research_tier": research.research_tier,
        "research_tier_reason": research.research_tier_reason,
    }


def _context_header(
    research: ResearchBundle,
    *,
    style_guide: str,
) -> str:
    style_guide_block = (
        f"STYLE GUIDE (hard rulebook):\n{style_guide}\n\n"
        if style_guide.strip()
        else "STYLE GUIDE: (none provided — use clear, professional PDP structure.)\n\n"
    )
    tier_note = ""
    if research.research_tier == "family_series":
        tier_note = (
            "RESEARCH TIER: family_series — evidence may describe the product family, "
            "not necessarily this exact SKU.\n\n"
        )
    elif research.research_tier == "competitor_proxy":
        tier_note = (
            "RESEARCH TIER: competitor_proxy — evidence is from competitor products, "
            "not the OEM manufacturer.\n\n"
        )
    return (
        f"Manufacturer: {research.normalized_manufacturer}\n"
        f"Manufacturer product number: {research.normalized_mpn}\n"
        f"Research tier: {research.research_tier}\n\n"
        f"{tier_note}"
        f"{style_guide_block}"
        f"VALIDATED SOURCE EVIDENCE:\n{research.evidence_text}\n"
    )


async def execute_research(
    *,
    manufacturer_name: str,
    manufacturer_product_number: str,
    product_family_hint: str = "",
) -> ResearchBundle:
    return await research_product(
        manufacturer=manufacturer_name,
        mpn=manufacturer_product_number,
        product_family_hint=product_family_hint,
    )


async def execute_llm_steps(
    research: ResearchBundle,
    payload: RunRequest | RunContinueRequest,
    *,
    prior_cost_collector=None,
    prior_timer=None,
) -> RunResult:
    settings = get_settings()
    deadline = time.monotonic() + settings.max_run_seconds
    raw_style = payload.style_guide_text or ""
    style_guide = style_guide_for_llm(raw_style)
    style_guide_truncated = bool(raw_style) and len(raw_style) > len(style_guide)

    with run_tracking() as (collector, timer):
        if prior_cost_collector is not None:
            collector.llm_events.extend(prior_cost_collector.llm_events)
            collector.external_costs.extend(prior_cost_collector.external_costs)
        if prior_timer is not None:
            timer.phases.extend(prior_timer.phases)

        source_records = [s.record for s in research.sources]
        audit = _research_audit(
            research,
            style_guide_truncated=style_guide_truncated,
            style_guide_provided=bool(style_guide.strip()),
        )
        manufacturer = research.normalized_manufacturer
        mpn = research.normalized_mpn
        context_header = _context_header(research, style_guide=style_guide)

        if time.monotonic() > deadline:
            return _incomplete(
                "Run exceeded 180s maximum runtime.",
                source_records,
                collector,
                timer,
                payload,
                style_guide_truncated,
                audit,
                manufacturer=manufacturer,
                mpn=mpn,
            )

        if not research.match_verified:
            return _incomplete(
                research.incomplete_reason or "Product match could not be verified.",
                source_records,
                collector,
                timer,
                payload,
                style_guide_truncated,
                audit,
                manufacturer=manufacturer,
                mpn=mpn,
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
                    manufacturer=manufacturer,
                    mpn=mpn,
                    step1_output=step_outputs.get(1),
                    step2_output=step_outputs.get(2),
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
                        manufacturer=manufacturer,
                        mpn=mpn,
                        step1_output=step_outputs.get(1),
                        step2_output=step_outputs.get(2),
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
                manufacturer=manufacturer,
                mpn=mpn,
                step1_output=step_outputs.get(1),
                step2_output=step_outputs.get(2),
            )

        steps_config = [
            {"name": payload.step1.name, "model": payload.step1.model, "prompt": payload.step1.prompt},
            {"name": payload.step2.name, "model": payload.step2.model, "prompt": payload.step2.prompt},
            {"name": payload.step3.name, "model": payload.step3.model, "prompt": payload.step3.prompt},
        ]
        report_html = render_internal_report(
            manufacturer=manufacturer,
            mpn=mpn,
            style_guide_filename=getattr(payload, "style_guide_filename", "") or "",
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


async def execute_run(payload: RunRequest) -> RunResult:
    collector = None
    timer = None
    with run_tracking() as (collector, timer):
        timer.start_phase("match_and_research")
        try:
            research = await execute_research(
                manufacturer_name=payload.manufacturer_name,
                manufacturer_product_number=payload.manufacturer_product_number,
                product_family_hint=payload.product_family_hint,
            )
        except (SerpapiError, FirecrawlError) as exc:
            timer.end_phase()
            return _incomplete(
                str(exc),
                [],
                collector,
                timer,
                payload,
                False,
                {"research_error": str(exc)},
                manufacturer=payload.manufacturer_name,
                mpn=payload.manufacturer_product_number,
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
                False,
                {"research_error": str(exc)},
                manufacturer=payload.manufacturer_name,
                mpn=payload.manufacturer_product_number,
            )
        timer.end_phase()

    assert collector is not None and timer is not None
    return await execute_llm_steps(research, payload, prior_cost_collector=collector, prior_timer=timer)


async def execute_run_continue(payload: RunContinueRequest) -> RunResult:
    research = get_research_session(payload.research_session_id)
    if research is None:
        return RunResult(
            status="incomplete",
            incomplete_reason="Incomplete: Research session expired or not found.",
            match_verified=False,
            audit={"research_session_id": payload.research_session_id},
        )
    result = await execute_llm_steps(research, payload)
    delete_research_session(payload.research_session_id)
    return result


def _incomplete(
    reason: str,
    sources,
    collector,
    timer,
    payload: RunRequest | RunContinueRequest,
    style_guide_truncated: bool,
    audit: dict,
    *,
    manufacturer: str,
    mpn: str,
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
        manufacturer=manufacturer,
        mpn=mpn,
        style_guide_filename=getattr(payload, "style_guide_filename", "") or "",
        style_guide_truncated=style_guide_truncated,
        steps=steps_config,
        sources=[s.model_dump() if hasattr(s, "model_dump") else s for s in sources],
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
