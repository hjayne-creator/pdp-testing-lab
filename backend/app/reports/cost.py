from __future__ import annotations

from app.models.schemas import CostLineItem, RuntimeLineItem
from app.observability.run_usage import ExternalCostRecord, LLMUsageRecord, RunTimer, RunUsageCollector


def build_cost_report(collector: RunUsageCollector) -> tuple[list[CostLineItem], float]:
    lines: list[CostLineItem] = []
    total = 0.0

    by_step: dict[str, LLMUsageRecord] = {}
    for event in collector.llm_events:
        if event.status != "success":
            continue
        key = event.step_name or "unknown"
        existing = by_step.get(key)
        if existing is None:
            by_step[key] = LLMUsageRecord(
                provider=event.provider,
                model=event.model,
                step_no=event.step_no,
                step_name=event.step_name,
                status=event.status,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                total_tokens=event.total_tokens,
                input_cost_usd=event.input_cost_usd,
                output_cost_usd=event.output_cost_usd,
                total_cost_usd=event.total_cost_usd,
            )
        else:
            existing.input_tokens += event.input_tokens
            existing.output_tokens += event.output_tokens
            existing.total_tokens += event.total_tokens
            existing.input_cost_usd += event.input_cost_usd
            existing.output_cost_usd += event.output_cost_usd
            existing.total_cost_usd += event.total_cost_usd

    for event in by_step.values():
        lines.append(
            CostLineItem(
                phase=event.step_name or "step",
                service="llm",
                model=event.model,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                input_cost_usd=round(event.input_cost_usd, 6),
                output_cost_usd=round(event.output_cost_usd, 6),
                total_cost_usd=round(event.total_cost_usd, 6),
            )
        )
        total += event.total_cost_usd

    external_by_service: dict[str, ExternalCostRecord] = {}
    for item in collector.external_costs:
        existing = external_by_service.get(item.service)
        if existing is None:
            external_by_service[item.service] = ExternalCostRecord(
                service=item.service,
                phase=item.phase,
                units=item.units,
                unit_cost_usd=item.unit_cost_usd,
                total_cost_usd=item.total_cost_usd,
            )
        else:
            existing.units += item.units
            existing.total_cost_usd += item.total_cost_usd

    for item in external_by_service.values():
        lines.append(
            CostLineItem(
                phase=item.phase,
                service=item.service,
                units=item.units,
                total_cost_usd=round(item.total_cost_usd, 6),
            )
        )
        total += item.total_cost_usd

    return lines, round(total, 6)


def build_runtime_report(timer: RunTimer) -> tuple[list[RuntimeLineItem], int]:
    lines = [RuntimeLineItem(phase=phase.name, duration_ms=phase.duration_ms) for phase in timer.phases]
    return lines, timer.total_ms
