"""DB table models，對應 spec §4.3。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _new_id() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Skill(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    name: str = Field(index=True)
    description: str = ""
    owner: str = ""
    path: str  # storage 資料夾路徑，例如 ./skills_storage/{id}/
    has_scripts: bool = False
    created_at: datetime = Field(default_factory=_utcnow)


class Agent(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    name: str = Field(index=True)
    model: str
    skill_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    instructions: str = ""
    owner: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class ScheduleCreatedBy(str, Enum):
    user = "user"
    agent = "agent"


class Schedule(SQLModel, table=True):
    id: str = Field(default_factory=_new_id, primary_key=True)
    agent_id: str = Field(foreign_key="agent.id", index=True)
    cron_expression: str
    enabled: bool = True
    created_by: ScheduleCreatedBy = ScheduleCreatedBy.user
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    run_input: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    # Agent 自建的排程一律從 enabled=False 開始，這個欄位維持 None 直到人工第一次
    # 核准（啟用）。使用者自己在頁面上設定的排程不需要審核，建立當下就補上這個
    # 時間戳。用來跟「原本啟用、之後被人工暫停」區分：後者 reviewed_at 已經有值，
    # 不該在「待審核」清單裡重新冒出來。
    reviewed_at: datetime | None = None


class RunLog(SQLModel, table=True):
    """非 spec 明列的資料表，但手動/排程執行後需要地方存結果讓前端顯示，先簡單記一筆。"""

    id: str = Field(default_factory=_new_id, primary_key=True)
    agent_id: str = Field(foreign_key="agent.id", index=True)
    schedule_id: str | None = Field(default=None, foreign_key="schedule.id")
    triggered_by: str = "user"  # "user" (手動執行) | "schedule"
    input_text: str = ""
    output_text: str = ""
    error_text: str | None = None
    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = None
