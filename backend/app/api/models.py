from __future__ import annotations

from fastapi import APIRouter
from sqlmodel import Session, select

from app.models.db import ModelCatalogEntry, get_engine
from app.models.schemas import ModelOption

router = APIRouter()


@router.get("", response_model=list[ModelOption])
def list_models() -> list[ModelOption]:
    with Session(get_engine()) as session:
        rows = session.exec(
            select(ModelCatalogEntry)
            .where(ModelCatalogEntry.active.is_(True))
            .order_by(ModelCatalogEntry.sort_order)
        ).all()
        return [
            ModelOption(id=r.model_id, label=r.label, provider=r.provider, description=r.description)
            for r in rows
        ]
