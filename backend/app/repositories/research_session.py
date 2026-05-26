"""Persist research snapshots for the two-step lab workflow."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlmodel import Session, select

from app.models.db import ResearchSession, get_engine
from app.models.schemas import SourceRecord
from app.research.searcher import ResearchBundle, ScrapedSource

logger = logging.getLogger(__name__)

SESSION_TTL_HOURS = 24


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_bundle(bundle: ResearchBundle) -> dict[str, Any]:
    return {
        "sources": [
            {"record": s.record.model_dump(), "markdown": s.markdown} for s in bundle.sources
        ],
        "evidence_text": bundle.evidence_text,
        "match_verified": bundle.match_verified,
        "incomplete_reason": bundle.incomplete_reason,
        "manufacturer_data_available": bundle.manufacturer_data_available,
        "fallback_ecommerce_used": bundle.fallback_ecommerce_used,
        "normalized_manufacturer": bundle.normalized_manufacturer,
        "normalized_mpn": bundle.normalized_mpn,
        "product_family_hint": bundle.product_family_hint,
        "research_tier": bundle.research_tier,
        "research_tier_reason": bundle.research_tier_reason,
    }


def _deserialize_bundle(data: dict[str, Any]) -> ResearchBundle:
    sources = [
        ScrapedSource(record=SourceRecord(**item["record"]), markdown=item["markdown"])
        for item in data.get("sources", [])
    ]
    return ResearchBundle(
        sources=sources,
        evidence_text=data.get("evidence_text", ""),
        match_verified=data.get("match_verified", False),
        incomplete_reason=data.get("incomplete_reason"),
        manufacturer_data_available=data.get("manufacturer_data_available", False),
        fallback_ecommerce_used=data.get("fallback_ecommerce_used", False),
        normalized_manufacturer=data.get("normalized_manufacturer", ""),
        normalized_mpn=data.get("normalized_mpn", ""),
        product_family_hint=data.get("product_family_hint", ""),
        research_tier=data.get("research_tier", "none"),
        research_tier_reason=data.get("research_tier_reason", ""),
    )


def prune_expired_sessions() -> int:
    deleted = 0
    with Session(get_engine()) as session:
        cutoff = _now()
        rows = session.exec(select(ResearchSession).where(ResearchSession.expires_at < cutoff)).all()
        for row in rows:
            session.delete(row)
            deleted += 1
        if deleted:
            session.commit()
    return deleted


def create_research_session(bundle: ResearchBundle) -> str:
    prune_expired_sessions()
    session_id = str(uuid.uuid4())
    expires_at = _now() + timedelta(hours=SESSION_TTL_HOURS)
    with Session(get_engine()) as session:
        session.add(
            ResearchSession(
                id=session_id,
                expires_at=expires_at,
                payload=_serialize_bundle(bundle),
            )
        )
        session.commit()
    return session_id


def get_research_session(session_id: str) -> ResearchBundle | None:
    prune_expired_sessions()
    with Session(get_engine()) as session:
        row = session.get(ResearchSession, session_id)
        if row is None:
            return None
        if row.expires_at < _now():
            session.delete(row)
            session.commit()
            return None
        try:
            return _deserialize_bundle(row.payload)
        except Exception:
            logger.exception("Failed to deserialize research session %s", session_id)
            return None


def delete_research_session(session_id: str) -> None:
    with Session(get_engine()) as session:
        row = session.get(ResearchSession, session_id)
        if row is not None:
            session.delete(row)
            session.commit()
