"""不需要 Redis/Celery 的排程執行方式：在 FastAPI process 裡跑一個
asyncio 背景迴圈，直接輪詢 DB 並執行到期的排程。

跟 worker/tasks.py（Celery 版本）做的事完全一樣，差別只在「誰來排程」：
- Celery 版：Beat 定期 tick -> worker process 執行（spec §7.1 原始設計，
  可以跑多個 worker、跟 web process 分開部署）
- 這裡：FastAPI process 自己起一個迴圈，每
  SCHEDULER_POLL_INTERVAL_SECONDS 秒跑一次，直接在同一個 process 裡執行

這個版本是給沒裝 Redis 的本機/POC 測試用。兩種 backend（見
app/config.py 的 SCHEDULER_BACKEND）不要同時開，否則同一筆排程可能被
跑兩次。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlmodel import Session

from app.agent_service import run_agent_once
from app.config import settings
from app.db import engine
from app.models import Agent
from app.schedule_service import compute_next_run_at, due_schedules

logger = logging.getLogger(__name__)


async def _run_due_schedules_once() -> None:
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        due = due_schedules(session, now=now)
        for schedule in due:
            # 先推進 next_run_at 再執行，避免下一輪 poll 重複挑到同一筆。
            schedule.next_run_at = compute_next_run_at(schedule.cron_expression, base=now)
            session.add(schedule)
            session.commit()

            agent = session.get(Agent, schedule.agent_id)
            if agent is None:
                continue

            try:
                await run_agent_once(
                    session,
                    agent,
                    run_input=schedule.run_input or "",
                    triggered_by="schedule",
                    schedule_id=schedule.id,
                )
            except Exception:  # 單筆排程失敗不該讓整個輪詢迴圈死掉
                logger.exception("in-process 排程執行失敗 schedule_id=%s", schedule.id)

            schedule.last_run_at = datetime.now(timezone.utc)
            session.add(schedule)
            session.commit()


async def scheduler_loop() -> None:
    interval = settings.scheduler_poll_interval_seconds
    logger.info("in-process scheduler 啟動，每 %s 秒輪詢一次", interval)
    while True:
        try:
            await _run_due_schedules_once()
        except Exception:
            logger.exception("in-process scheduler 輪詢時發生例外")
        await asyncio.sleep(interval)
