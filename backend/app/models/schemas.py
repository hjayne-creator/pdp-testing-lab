from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class StepConfig(BaseModel):
    name: str
    prompt: str
    model: str


class RunRequest(BaseModel):
    manufacturer_name: str
    manufacturer_product_number: str
    style_guide_text: str
    style_guide_filename: str = ""
    step1: StepConfig
    step2: StepConfig
    step3: StepConfig


class CostLineItem(BaseModel):
    phase: str
    service: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    input_cost_usd: float = 0.0
    output_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    units: int | None = None


class RuntimeLineItem(BaseModel):
    phase: str
    duration_ms: int


class SourceRecord(BaseModel):
    url: str
    title: str
    tier: str
    domain: str
    exact_mpn_found: bool
    scrape_ok: bool
    error: str | None = None


class RunResult(BaseModel):
    status: Literal["complete", "incomplete"]
    incomplete_reason: str | None = None
    final_content: str | None = None
    style_guide_truncated: bool = False
    match_verified: bool = False
    sources: list[SourceRecord] = Field(default_factory=list)
    cost_lines: list[CostLineItem] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    runtime_lines: list[RuntimeLineItem] = Field(default_factory=list)
    total_runtime_ms: int = 0
    step1_output: str | None = None
    step2_output: str | None = None
    internal_report_html: str | None = None
    audit: dict[str, Any] = Field(default_factory=dict)


class LabSettingsResponse(BaseModel):
    manufacturer_name: str
    manufacturer_product_number: str
    style_guide_filename: str
    style_guide_text: str
    step1_name: str
    step1_prompt: str
    step1_model: str
    step2_name: str
    step2_prompt: str
    step2_model: str
    step3_name: str
    step3_prompt: str
    step3_model: str


class LabSettingsUpdate(BaseModel):
    manufacturer_name: str | None = None
    manufacturer_product_number: str | None = None
    style_guide_filename: str | None = None
    style_guide_text: str | None = None
    step1_name: str | None = None
    step1_prompt: str | None = None
    step1_model: str | None = None
    step2_name: str | None = None
    step2_prompt: str | None = None
    step2_model: str | None = None
    step3_name: str | None = None
    step3_prompt: str | None = None
    step3_model: str | None = None


class RunSummary(BaseModel):
    id: int
    created_at: datetime
    manufacturer_name: str
    manufacturer_product_number: str
    status: Literal["complete", "incomplete"]
    match_verified: bool
    incomplete_reason: str | None = None
    total_cost_usd: float
    total_runtime_ms: int
    style_guide_filename: str = ""


class RunListResponse(BaseModel):
    runs: list[RunSummary]
    total: int


class ModelOption(BaseModel):
    id: str
    label: str
    provider: str
    description: str = ""


class PriceCardOut(BaseModel):
    id: int
    provider: str
    model: str
    input_per_million_usd: float
    output_per_million_usd: float
    active: bool


class PriceCardUpdate(BaseModel):
    provider: str
    model: str
    input_per_million_usd: float
    output_per_million_usd: float
    active: bool = True
    notes: str | None = None
