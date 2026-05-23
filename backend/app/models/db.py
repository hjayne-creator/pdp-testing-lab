"""SQLModel tables and engine setup."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Session, SQLModel, create_engine, select

from app.config import get_settings
from app.domain_blocklist import (
    DEFAULT_AUTHORIZED_DISTRIBUTOR_SEEDS,
    DEFAULT_BLOCKED_DOMAIN_SEEDS,
    normalize_blocked_domain_key,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LabSettings(SQLModel, table=True):
    id: Optional[int] = Field(default=1, primary_key=True)
    manufacturer_name: str = ""
    manufacturer_product_number: str = ""
    style_guide_filename: str = ""
    style_guide_text: str = ""
    step1_name: str = "Research"
    step1_prompt: str = ""
    step1_model: str = "gpt-5"
    step2_name: str = "Writing"
    step2_prompt: str = ""
    step2_model: str = "claude-sonnet-4-6"
    step3_name: str = "Fact-check and edit"
    step3_prompt: str = ""
    step3_model: str = "claude-sonnet-4-6"
    updated_at: datetime = Field(default_factory=_now)


class BlockedDomain(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    domain: str = Field(unique=True, index=True)


class AuthorizedDistributor(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    domain: str = Field(unique=True, index=True)


class ModelCatalogEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    model_id: str = Field(unique=True, index=True)
    label: str
    provider: str
    description: str = ""
    sort_order: int = 0
    active: bool = True


class LLMPriceCard(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(index=True)
    model: str = Field(index=True)
    input_per_million_usd: float = 0.0
    output_per_million_usd: float = 0.0
    effective_from: datetime = Field(default_factory=_now, index=True)
    effective_to: Optional[datetime] = Field(default=None, index=True)
    active: bool = Field(default=True, index=True)
    notes: Optional[str] = None


class ServicePriceCard(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    service: str = Field(index=True)
    unit_label: str = "call"
    cost_per_unit_usd: float = 0.0
    active: bool = True


class LabRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_now, index=True)
    manufacturer_name: str = ""
    manufacturer_product_number: str = ""
    status: str = ""
    match_verified: bool = False
    incomplete_reason: Optional[str] = None
    total_cost_usd: float = 0.0
    total_runtime_ms: int = 0
    style_guide_filename: str = ""
    style_guide_hash: Optional[str] = None
    result_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
        _engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)
    return _engine


DEFAULT_STEP1_PROMPT = """Review the validated source evidence for the exact product identified below.
Summarize only facts that are clearly supported by the provided sources for this exact manufacturer product number.
Do not add assumptions, category norms, or unsupported claims.
Flag any ambiguous variant-grouped content that should be excluded.

Output a structured research brief for the writing step."""

DEFAULT_STEP2_PROMPT = """Write copy-and-paste-ready product detail page content for the exact product below.
Use only the validated research brief and source evidence.
Follow the style guide as a hard rulebook.
Do not include source citations, research notes, or URLs in the output.
Use only sections the style guide and evidence support."""

DEFAULT_STEP3_PROMPT = """Fact-check and edit the draft product detail page content below.
Remove any unsupported, ambiguous, or conflicting claims rather than softening them.
Accuracy beats completeness — shorter content is acceptable.
Ensure the style guide is fully respected.
Return only the final WYSIWYG content with no citations or research notes."""


def init_db() -> None:
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        if session.get(LabSettings, 1) is None:
            session.add(
                LabSettings(
                    id=1,
                    step1_prompt=DEFAULT_STEP1_PROMPT,
                    step2_prompt=DEFAULT_STEP2_PROMPT,
                    step3_prompt=DEFAULT_STEP3_PROMPT,
                )
            )

        existing_blocked = {r.domain for r in session.exec(select(BlockedDomain)).all()}
        for seed in DEFAULT_BLOCKED_DOMAIN_SEEDS:
            domain = normalize_blocked_domain_key(seed)
            if domain and domain not in existing_blocked:
                session.add(BlockedDomain(domain=domain))

        existing_auth = {r.domain for r in session.exec(select(AuthorizedDistributor)).all()}
        for seed in DEFAULT_AUTHORIZED_DISTRIBUTOR_SEEDS:
            domain = normalize_blocked_domain_key(seed)
            if domain and domain not in existing_auth:
                session.add(AuthorizedDistributor(domain=domain))

        existing_models = {r.model_id for r in session.exec(select(ModelCatalogEntry)).all()}
        default_models = [
            ("gpt-5", "GPT-5", "openai", "OpenAI flagship model.", 1),
            ("claude-sonnet-4-6", "Claude Sonnet 4.6", "anthropic", "Anthropic mid-tier model.", 2),
            ("grok-4-1-fast-reasoning", "Grok 4.1 Fast (reasoning)", "xai", "xAI reasoning model.", 3),
        ]
        for model_id, label, provider, description, sort_order in default_models:
            if model_id not in existing_models:
                session.add(
                    ModelCatalogEntry(
                        model_id=model_id,
                        label=label,
                        provider=provider,
                        description=description,
                        sort_order=sort_order,
                    )
                )

        existing_prices = session.exec(select(LLMPriceCard)).first()
        if existing_prices is None:
            session.add_all(
                [
                    LLMPriceCard(provider="openai", model="gpt-5", input_per_million_usd=2.50, output_per_million_usd=10.0),
                    LLMPriceCard(provider="anthropic", model="claude-sonnet-4-6", input_per_million_usd=3.0, output_per_million_usd=15.0),
                    LLMPriceCard(provider="xai", model="grok-4-1-fast-reasoning", input_per_million_usd=1.25, output_per_million_usd=2.50),
                ]
            )

        settings = get_settings()
        existing_service = {r.service for r in session.exec(select(ServicePriceCard)).all()}
        service_seeds = [
            ("serpapi", "search", settings.serpapi_cost_usd),
            ("firecrawl", "scrape", settings.firecrawl_cost_usd),
        ]
        for service, unit_label, cost in service_seeds:
            if service not in existing_service:
                session.add(ServicePriceCard(service=service, unit_label=unit_label, cost_per_unit_usd=cost))

        session.commit()
