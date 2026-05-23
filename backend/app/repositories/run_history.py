"""Persist and query lab run history."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, col, func, select

from app.config import get_settings
from app.models.db import LabRun, get_engine
from app.models.schemas import RunListResponse, RunResult, RunSummary

logger = logging.getLogger(__name__)

_INCOMPLETE_REASON_MAX = 500


@dataclass
class RunSaveMetadata:
    manufacturer_name: str
    manufacturer_product_number: str
    style_guide_filename: str = ""
    style_guide_hash: str | None = None


def _truncate_reason(reason: str | None) -> str | None:
    if not reason:
        return None
    if len(reason) <= _INCOMPLETE_REASON_MAX:
        return reason
    return reason[: _INCOMPLETE_REASON_MAX - 3] + "..."


def _row_to_summary(row: LabRun) -> RunSummary:
    return RunSummary(
        id=row.id or 0,
        created_at=row.created_at,
        manufacturer_name=row.manufacturer_name,
        manufacturer_product_number=row.manufacturer_product_number,
        status=row.status,  # type: ignore[arg-type]
        match_verified=row.match_verified,
        incomplete_reason=row.incomplete_reason,
        total_cost_usd=row.total_cost_usd,
        total_runtime_ms=row.total_runtime_ms,
        style_guide_filename=row.style_guide_filename,
    )


def prune_runs() -> int:
    """Apply count and age retention limits. Returns number of rows deleted."""
    settings = get_settings()
    deleted = 0
    with Session(get_engine()) as session:
        if settings.run_history_max_age_days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=settings.run_history_max_age_days)
            old_rows = session.exec(select(LabRun).where(LabRun.created_at < cutoff)).all()
            for row in old_rows:
                session.delete(row)
                deleted += 1

        count = session.exec(select(func.count()).select_from(LabRun)).one()
        if count > settings.run_history_max_count:
            excess = count - settings.run_history_max_count
            oldest = session.exec(
                select(LabRun).order_by(col(LabRun.created_at).asc()).limit(excess)
            ).all()
            for row in oldest:
                session.delete(row)
                deleted += 1

        if deleted:
            session.commit()
    return deleted


def save_run(result: RunResult, meta: RunSaveMetadata) -> int | None:
    """Persist a completed run. Returns new row id or None on failure."""
    try:
        payload = result.model_dump(mode="json")
        row = LabRun(
            manufacturer_name=meta.manufacturer_name,
            manufacturer_product_number=meta.manufacturer_product_number,
            status=result.status,
            match_verified=result.match_verified,
            incomplete_reason=_truncate_reason(result.incomplete_reason),
            total_cost_usd=result.total_cost_usd,
            total_runtime_ms=result.total_runtime_ms,
            style_guide_filename=meta.style_guide_filename,
            style_guide_hash=meta.style_guide_hash,
            result_json=payload,
        )
        with Session(get_engine()) as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            run_id = row.id
        try:
            prune_runs()
        except Exception:
            logger.exception("Run history retention prune failed")
        return run_id
    except Exception:
        logger.exception("Failed to save run history")
        return None


def list_runs(*, limit: int = 50, offset: int = 0) -> RunListResponse:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    with Session(get_engine()) as session:
        total = session.exec(select(func.count()).select_from(LabRun)).one()
        rows = session.exec(
            select(LabRun).order_by(col(LabRun.created_at).desc()).offset(offset).limit(limit)
        ).all()
    return RunListResponse(runs=[_row_to_summary(r) for r in rows], total=total)


def get_run(run_id: int) -> RunResult | None:
    with Session(get_engine()) as session:
        row = session.get(LabRun, run_id)
    if row is None:
        return None
    return RunResult.model_validate(row.result_json)


def delete_run(run_id: int) -> bool:
    with Session(get_engine()) as session:
        row = session.get(LabRun, run_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
    return True
