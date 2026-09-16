from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR, settings
from app.db import init_db
from app.inprocess_scheduler import scheduler_loop
from app.routers import agents, schedules, skills, ui

logger = logging.getLogger(__name__)

app = FastAPI(title="Skill 掛載 Agent POC")


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    if settings.scheduler_backend == "inprocess":
        app.state.scheduler_task = asyncio.create_task(scheduler_loop())
    elif settings.scheduler_backend not in ("celery", "off"):
        logger.warning("未知的 SCHEDULER_BACKEND=%r，排程不會自動執行", settings.scheduler_backend)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    task = getattr(app.state, "scheduler_task", None)
    if task is not None:
        task.cancel()


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

app.include_router(skills.router)
app.include_router(agents.router)
app.include_router(schedules.router)
app.include_router(ui.router)
