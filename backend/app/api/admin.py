from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select

from app.models.db import LLMPriceCard, get_engine
from app.models.schemas import PriceCardOut, PriceCardUpdate

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/price-cards", response_model=list[PriceCardOut])
def list_price_cards() -> list[PriceCardOut]:
    with Session(get_engine()) as session:
        rows = session.exec(
            select(LLMPriceCard).order_by(LLMPriceCard.provider, LLMPriceCard.model)
        ).all()
        return [
            PriceCardOut(
                id=r.id or 0,
                provider=r.provider,
                model=r.model,
                input_per_million_usd=r.input_per_million_usd,
                output_per_million_usd=r.output_per_million_usd,
                active=r.active,
            )
            for r in rows
        ]


@router.post("/price-cards", response_model=PriceCardOut)
def upsert_price_card(payload: PriceCardUpdate) -> PriceCardOut:
    with Session(get_engine()) as session:
        existing = session.exec(
            select(LLMPriceCard).where(
                LLMPriceCard.provider == payload.provider,
                LLMPriceCard.model == payload.model,
                LLMPriceCard.active.is_(True),
            )
        ).first()
        if existing is not None:
            existing.active = False
            existing.effective_to = _now()
            session.add(existing)

        row = LLMPriceCard(
            provider=payload.provider,
            model=payload.model,
            input_per_million_usd=payload.input_per_million_usd,
            output_per_million_usd=payload.output_per_million_usd,
            active=payload.active,
            notes=payload.notes,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return PriceCardOut(
            id=row.id or 0,
            provider=row.provider,
            model=row.model,
            input_per_million_usd=row.input_per_million_usd,
            output_per_million_usd=row.output_per_million_usd,
            active=row.active,
        )


@router.delete("/price-cards/{card_id}")
def deactivate_price_card(card_id: int) -> dict:
    with Session(get_engine()) as session:
        row = session.get(LLMPriceCard, card_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Price card not found.")
        row.active = False
        row.effective_to = _now()
        session.add(row)
        session.commit()
    return {"ok": True}
