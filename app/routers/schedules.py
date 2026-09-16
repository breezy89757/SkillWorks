from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.schedule_service import ScheduleError, update_schedule
from app.schemas import ScheduleOut, ScheduleUpdate

router = APIRouter(prefix="/schedules", tags=["schedules"])


@router.patch("/{schedule_id}", response_model=ScheduleOut)
def patch_schedule(
    schedule_id: str, payload: ScheduleUpdate, session: Session = Depends(get_session)
) -> ScheduleOut:
    try:
        schedule = update_schedule(
            session,
            schedule_id,
            enabled=payload.enabled,
            cron_expression=payload.cron_expression,
            run_input=payload.run_input,
        )
    except ScheduleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ScheduleOut.model_validate(schedule, from_attributes=True)
