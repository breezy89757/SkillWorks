"""Celery app：broker/backend 用 Redis，對應 spec §7.1。

排程設定本身存 DB（見 app/models.py 的 Schedule），不寫死在 celery beat 的
static schedule。beat 這裡只靜態排一個固定頻率的「輪詢」任務
(poll_due_schedules)，由它去查 DB 裡哪些排程到期，再各自 dispatch 一個
run_scheduled_agent 任務——新增/修改/刪除 DB 裡的排程不需要重啟任何服務。
"""

from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "skill_agent_poc",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["worker.tasks"],
)

celery_app.conf.beat_schedule = {
    "poll-due-schedules": {
        "task": "worker.tasks.poll_due_schedules",
        "schedule": float(settings.scheduler_poll_interval_seconds),
    },
}
celery_app.conf.timezone = "UTC"
