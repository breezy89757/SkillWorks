"""JSON API 的 request / response schema（非 DB table model）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models import ScheduleCreatedBy


class SkillOut(BaseModel):
    id: str
    name: str
    description: str
    owner: str
    has_scripts: bool
    created_at: datetime


class AgentCreate(BaseModel):
    name: str
    model: str
    skill_ids: list[str] = []
    instructions: str = ""
    owner: str = ""


class AgentOut(BaseModel):
    id: str
    name: str
    model: str
    skill_ids: list[str]
    instructions: str
    owner: str
    created_at: datetime


class AgentRunRequest(BaseModel):
    input: str


class AgentRunResult(BaseModel):
    id: str
    agent_id: str
    triggered_by: str
    input_text: str
    output_text: str
    error_text: str | None
    started_at: datetime
    finished_at: datetime | None


class ScheduleCreate(BaseModel):
    cron_expression: str
    run_input: str | None = None
    enabled: bool = True


class ScheduleOut(BaseModel):
    id: str
    agent_id: str
    cron_expression: str
    enabled: bool
    created_by: ScheduleCreatedBy
    last_run_at: datetime | None
    next_run_at: datetime | None
    run_input: str | None
    created_at: datetime


class ScheduleUpdate(BaseModel):
    cron_expression: str | None = None
    run_input: str | None = None
    enabled: bool | None = None
