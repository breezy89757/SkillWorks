from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.agent_service import run_agent_once
from app.db import get_session
from app.models import Agent, ScheduleCreatedBy
from app.schedule_service import ScheduleError, create_schedule, list_schedules
from app.schemas import (
    AgentCreate,
    AgentOut,
    AgentRunRequest,
    AgentRunResult,
    ScheduleCreate,
    ScheduleOut,
)

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentOut])
def list_agents(session: Session = Depends(get_session)) -> list[AgentOut]:
    agents = session.exec(select(Agent).order_by(Agent.created_at.desc())).all()
    return [AgentOut.model_validate(a, from_attributes=True) for a in agents]


@router.post("", response_model=AgentOut)
def create_agent(payload: AgentCreate, session: Session = Depends(get_session)) -> AgentOut:
    agent = Agent(**payload.model_dump())
    session.add(agent)
    session.commit()
    session.refresh(agent)
    return AgentOut.model_validate(agent, from_attributes=True)


def _get_agent_or_404(session: Session, agent_id: str) -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"找不到 agent_id={agent_id}")
    return agent


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: str, session: Session = Depends(get_session)) -> AgentOut:
    agent = _get_agent_or_404(session, agent_id)
    return AgentOut.model_validate(agent, from_attributes=True)


@router.post("/{agent_id}/run", response_model=AgentRunResult)
async def run_agent(
    agent_id: str, payload: AgentRunRequest, session: Session = Depends(get_session)
) -> AgentRunResult:
    agent = _get_agent_or_404(session, agent_id)
    log = await run_agent_once(session, agent, run_input=payload.input, triggered_by="user")
    return AgentRunResult.model_validate(log, from_attributes=True)


@router.post("/{agent_id}/schedules", response_model=ScheduleOut)
def create_agent_schedule(
    agent_id: str, payload: ScheduleCreate, session: Session = Depends(get_session)
) -> ScheduleOut:
    _get_agent_or_404(session, agent_id)
    try:
        schedule = create_schedule(
            session,
            agent_id=agent_id,
            cron_expression=payload.cron_expression,
            created_by=ScheduleCreatedBy.user,
            run_input=payload.run_input,
            enabled=payload.enabled,
        )
    except ScheduleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ScheduleOut.model_validate(schedule, from_attributes=True)


@router.get("/{agent_id}/schedules", response_model=list[ScheduleOut])
def get_agent_schedules(agent_id: str, session: Session = Depends(get_session)) -> list[ScheduleOut]:
    _get_agent_or_404(session, agent_id)
    schedules = list_schedules(session, agent_id)
    return [ScheduleOut.model_validate(s, from_attributes=True) for s in schedules]
