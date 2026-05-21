from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlmodel import Session, select

from app.models.db import LabSettings, get_engine
from app.models.schemas import LabSettingsResponse, LabSettingsUpdate

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_or_create_settings(session: Session) -> LabSettings:
    row = session.get(LabSettings, 1)
    if row is None:
        row = LabSettings(id=1)
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


@router.get("", response_model=LabSettingsResponse)
def get_settings_state() -> LabSettingsResponse:
    with Session(get_engine()) as session:
        row = _get_or_create_settings(session)
        return LabSettingsResponse(
            manufacturer_name=row.manufacturer_name,
            manufacturer_product_number=row.manufacturer_product_number,
            style_guide_filename=row.style_guide_filename,
            style_guide_text=row.style_guide_text,
            step1_name=row.step1_name,
            step1_prompt=row.step1_prompt,
            step1_model=row.step1_model,
            step2_name=row.step2_name,
            step2_prompt=row.step2_prompt,
            step2_model=row.step2_model,
            step3_name=row.step3_name,
            step3_prompt=row.step3_prompt,
            step3_model=row.step3_model,
        )


@router.put("", response_model=LabSettingsResponse)
def update_settings_state(payload: LabSettingsUpdate) -> LabSettingsResponse:
    with Session(get_engine()) as session:
        row = _get_or_create_settings(session)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
        row.updated_at = _now()
        session.add(row)
        session.commit()
        session.refresh(row)
        return LabSettingsResponse(
            manufacturer_name=row.manufacturer_name,
            manufacturer_product_number=row.manufacturer_product_number,
            style_guide_filename=row.style_guide_filename,
            style_guide_text=row.style_guide_text,
            step1_name=row.step1_name,
            step1_prompt=row.step1_prompt,
            step1_model=row.step1_model,
            step2_name=row.step2_name,
            step2_prompt=row.step2_prompt,
            step2_model=row.step2_model,
            step3_name=row.step3_name,
            step3_prompt=row.step3_prompt,
            step3_model=row.step3_model,
        )
