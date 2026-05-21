"""In-memory usage and timing collection for a single lab run."""
from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.observability.usage_extract import extract_anthropic_usage, extract_openai_usage
from app.models.db import LLMPriceCard, get_engine

Provider = str


@dataclass
class LLMUsageRecord:
    provider: Provider
    model: str
    step_no: int | None
    step_name: str | None
    status: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    input_cost_usd: float = 0.0
    output_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    latency_ms: int = 0
    error: str | None = None


@dataclass
class ExternalCostRecord:
    service: str
    phase: str
    units: int
    unit_cost_usd: float
    total_cost_usd: float


@dataclass
class RunUsageCollector:
    llm_events: list[LLMUsageRecord] = field(default_factory=list)
    external_costs: list[ExternalCostRecord] = field(default_factory=list)
    step_no: int | None = None
    step_name: str | None = None


@dataclass
class PhaseTimer:
    name: str
    started_at: float
    ended_at: float | None = None

    @property
    def duration_ms(self) -> int:
        end = self.ended_at if self.ended_at is not None else time.monotonic()
        return int((end - self.started_at) * 1000)


@dataclass
class RunTimer:
    started_at: float = field(default_factory=time.monotonic)
    phases: list[PhaseTimer] = field(default_factory=list)
    _active: PhaseTimer | None = None

    def start_phase(self, name: str) -> None:
        if self._active is not None:
            self.end_phase()
        self._active = PhaseTimer(name=name, started_at=time.monotonic())

    def end_phase(self) -> None:
        if self._active is None:
            return
        self._active.ended_at = time.monotonic()
        self.phases.append(self._active)
        self._active = None

    def finish(self) -> None:
        self.end_phase()

    @property
    def total_ms(self) -> int:
        end = time.monotonic()
        return int((end - self.started_at) * 1000)


_COLLECTOR: ContextVar[RunUsageCollector | None] = ContextVar("run_usage_collector", default=None)
_TIMER: ContextVar[RunTimer | None] = ContextVar("run_timer", default=None)


def monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_price_card(*, provider: str, model: str, now: datetime) -> LLMPriceCard | None:
    with Session(get_engine()) as session:
        return session.exec(
            select(LLMPriceCard)
            .where(
                LLMPriceCard.provider == provider,
                LLMPriceCard.model == model,
                LLMPriceCard.active.is_(True),
                LLMPriceCard.effective_from <= now,
            )
            .where((LLMPriceCard.effective_to.is_(None)) | (LLMPriceCard.effective_to > now))
            .order_by(LLMPriceCard.effective_from.desc())
        ).first()


def _per_million_to_cost(token_count: int, per_million_usd: float) -> float:
    if token_count <= 0 or per_million_usd <= 0:
        return 0.0
    return (token_count / 1_000_000.0) * per_million_usd


@contextmanager
def run_tracking():
    collector = RunUsageCollector()
    timer = RunTimer()
    c_token: Token = _COLLECTOR.set(collector)
    t_token: Token = _TIMER.set(timer)
    try:
        yield collector, timer
    finally:
        timer.finish()
        _COLLECTOR.reset(c_token)
        _TIMER.reset(t_token)


@contextmanager
def llm_step_context(*, step_no: int, step_name: str):
    collector = _COLLECTOR.get()
    if collector is not None:
        collector.step_no = step_no
        collector.step_name = step_name
    timer = _TIMER.get()
    if timer is not None:
        timer.start_phase(step_name)
    try:
        yield
    finally:
        if timer is not None:
            timer.end_phase()


def log_external_cost(*, service: str, phase: str, units: int, unit_cost_usd: float) -> None:
    collector = _COLLECTOR.get()
    if collector is None:
        return
    collector.external_costs.append(
        ExternalCostRecord(
            service=service,
            phase=phase,
            units=units,
            unit_cost_usd=unit_cost_usd,
            total_cost_usd=units * unit_cost_usd,
        )
    )


def log_llm_usage(
    *,
    provider: str,
    model: str,
    status: str,
    attempt_number: int,
    started_at_ms: int,
    response: Any = None,
    error: str | None = None,
) -> None:
    collector = _COLLECTOR.get()
    if collector is None:
        return

    if provider == "anthropic":
        usage = extract_anthropic_usage(response)
    else:
        usage = extract_openai_usage(response)

    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

    price_card = _resolve_price_card(provider=provider, model=model, now=_now())
    input_cost = 0.0
    output_cost = 0.0
    if price_card is not None:
        input_cost = _per_million_to_cost(input_tokens, price_card.input_per_million_usd)
        output_cost = _per_million_to_cost(output_tokens, price_card.output_per_million_usd)

    collector.llm_events.append(
        LLMUsageRecord(
            provider=provider,
            model=model,
            step_no=collector.step_no,
            step_name=collector.step_name,
            status=status,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            total_cost_usd=input_cost + output_cost,
            latency_ms=int(time.monotonic() * 1000) - started_at_ms,
            error=error,
        )
    )
