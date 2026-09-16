"""Celery tasks，對應 spec §7.1：

- `poll_due_schedules`：Beat 定期呼叫，輪詢 DB 裡 enabled=true 且到期的排程。
- `run_scheduled_agent`：Worker 實際執行，走跟手動執行完全相同的路徑
  （app.agent_service.run_agent_once），執行完更新 last_run_at / next_run_at。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlmodel import Session

from app.agent_service import run_agent_once
from app.db import engine
from app.models import Agent, Schedule
from app.schedule_service import compute_next_run_at, due_schedules
from worker.celery_app import celery_app


@celery_app.task(name="worker.tasks.poll_due_schedules")
def poll_due_schedules() -> int:
    now = datetime.now(timezone.utc)
    dispatched = 0
    with Session(engine) as session:
        for schedule in due_schedules(session, now=now):
            # 先推進 next_run_at 再 dispatch，避免同一筆排程在還沒跑完前
            # 被下一次 poll 重複挑到。
            schedule.next_run_at = compute_next_run_at(schedule.cron_expression, base=now)
            session.add(schedule)
            session.commit()

            run_scheduled_agent.delay(schedule.id)
            dispatched += 1
    return dispatched


@celery_app.task(name="worker.tasks.run_scheduled_agent")
def run_scheduled_agent(schedule_id: str) -> None:
    with Session(engine) as session:
        schedule = session.get(Schedule, schedule_id)
        if schedule is None or not schedule.enabled:
            return
        agent = session.get(Agent, schedule.agent_id)
        if agent is None:
            return

        asyncio.run(
            run_agent_once(
                session,
                agent,
                run_input=schedule.run_input or "",
                triggered_by="schedule",
                schedule_id=schedule.id,
            )
        )

        schedule.last_run_at = datetime.now(timezone.utc)
        session.add(schedule)
        session.commit()
