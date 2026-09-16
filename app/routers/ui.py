"""Jinja2 server-rendered 表單頁面，對應 spec §4.1。

跟 routers/skills.py、agents.py、schedules.py 的 JSON API 分開，直接呼叫
service 層函式（不透過 HTTP 呼叫自己的 API），避免重工。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app import skills_service
from app.agent_service import run_agent_once
from app.config import BASE_DIR
from app.db import get_session
from app.models import Agent, RunLog, Schedule, ScheduleCreatedBy
from app.schedule_service import (
    ScheduleError,
    create_schedule,
    is_pending_review,
    list_all_schedules,
    list_schedules,
    update_schedule,
)

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def _relative_time(dt: datetime | None) -> str:
    """"4 天前" 這種相對時間顯示，排程總覽頁用。"""
    if dt is None:
        return "-"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    seconds = (datetime.now(timezone.utc) - dt).total_seconds()
    if seconds < 60:
        return "剛剛"
    if seconds < 3600:
        return f"{int(seconds // 60)} 分鐘前"
    if seconds < 86400:
        return f"{int(seconds // 3600)} 小時前"
    days = int(seconds // 86400)
    if days < 30:
        return f"{days} 天前"
    if days < 365:
        return f"{days // 30} 個月前"
    return f"{days // 365} 年前"


templates.env.filters["relative"] = _relative_time
templates.env.globals["is_pending_review"] = is_pending_review


@router.get("/")
def home() -> RedirectResponse:
    return RedirectResponse(url="/ui/agents")


# ---------- Skills ----------


@router.get("/ui/skills")
def skills_page(request: Request, session: Session = Depends(get_session)):
    skills = skills_service.list_skills(session)
    return templates.TemplateResponse(
        request,
        "skills/list.html",
        {"skills": skills, "error": request.query_params.get("error"), "active": "skills"},
    )


@router.post("/ui/skills/upload")
async def upload_skill_ui(file: UploadFile, session: Session = Depends(get_session)):
    try:
        await skills_service.upload_skill(session, file)
    except skills_service.SkillValidationError as exc:
        return RedirectResponse(url=f"/ui/skills?error={exc}", status_code=303)
    return RedirectResponse(url="/ui/skills", status_code=303)


# ---------- Agents ----------


@router.get("/ui/agents")
def agents_page(request: Request, session: Session = Depends(get_session)):
    agents = session.exec(select(Agent).order_by(Agent.created_at.desc())).all()
    return templates.TemplateResponse(request, "agents/list.html", {"agents": agents, "active": "agents"})


@router.get("/ui/agents/new")
def new_agent_page(request: Request, session: Session = Depends(get_session)):
    skills = skills_service.list_skills(session)
    return templates.TemplateResponse(request, "agents/form.html", {"skills": skills, "active": "agents"})


@router.post("/ui/agents/new")
def create_agent_ui(
    name: str = Form(...),
    model: str = Form(...),
    instructions: str = Form(""),
    owner: str = Form(""),
    skill_ids: list[str] = Form([]),
    session: Session = Depends(get_session),
):
    agent = Agent(name=name, model=model, instructions=instructions, owner=owner, skill_ids=skill_ids)
    session.add(agent)
    session.commit()
    session.refresh(agent)
    return RedirectResponse(url=f"/ui/agents/{agent.id}", status_code=303)


@router.get("/ui/agents/{agent_id}")
def agent_detail_page(agent_id: str, request: Request, session: Session = Depends(get_session)):
    agent = session.get(Agent, agent_id)
    if agent is None:
        return templates.TemplateResponse(request, "not_found.html", {"kind": "agent", "id": agent_id}, status_code=404)

    selected_skills = skills_service.get_skills_by_ids(session, agent.skill_ids)
    run_logs = session.exec(
        select(RunLog).where(RunLog.agent_id == agent_id).order_by(RunLog.started_at.desc()).limit(10)
    ).all()
    schedules = list_schedules(session, agent_id)
    pending_count = sum(1 for s in schedules if is_pending_review(s))
    return templates.TemplateResponse(
        request,
        "agents/detail.html",
        {
            "agent": agent,
            "selected_skills": selected_skills,
            "run_logs": run_logs,
            "pending_count": pending_count,
            "active": "agents",
        },
    )


@router.post("/ui/agents/{agent_id}/run")
async def run_agent_ui(agent_id: str, run_input: str = Form(""), session: Session = Depends(get_session)):
    agent = session.get(Agent, agent_id)
    if agent is not None:
        await run_agent_once(session, agent, run_input=run_input, triggered_by="user")
    return RedirectResponse(url=f"/ui/agents/{agent_id}", status_code=303)


# ---------- Schedules ----------


@router.get("/ui/schedules")
def schedules_dashboard_page(request: Request, session: Session = Depends(get_session)):
    rows = list_all_schedules(session)
    pending = [(s, a) for s, a in rows if is_pending_review(s)]
    others = [(s, a) for s, a in rows if not is_pending_review(s)]
    return templates.TemplateResponse(
        request,
        "schedules/dashboard.html",
        {"pending": pending, "others": others, "active": "schedules"},
    )


@router.get("/ui/agents/{agent_id}/schedules")
def agent_schedules_page(agent_id: str, request: Request, session: Session = Depends(get_session)):
    agent = session.get(Agent, agent_id)
    if agent is None:
        return templates.TemplateResponse(request, "not_found.html", {"kind": "agent", "id": agent_id}, status_code=404)
    schedules = list_schedules(session, agent_id)
    return templates.TemplateResponse(
        request,
        "schedules/list.html",
        {
            "agent": agent,
            "schedules": schedules,
            "error": request.query_params.get("error"),
            "active": "agents",
        },
    )


@router.post("/ui/agents/{agent_id}/schedules")
def create_schedule_ui(
    agent_id: str,
    cron_expression: str = Form(...),
    run_input: str = Form(""),
    session: Session = Depends(get_session),
):
    try:
        create_schedule(
            session,
            agent_id=agent_id,
            cron_expression=cron_expression,
            created_by=ScheduleCreatedBy.user,
            run_input=run_input or None,
        )
    except ScheduleError as exc:
        return RedirectResponse(url=f"/ui/agents/{agent_id}/schedules?error={exc}", status_code=303)
    return RedirectResponse(url=f"/ui/agents/{agent_id}/schedules", status_code=303)


@router.post("/ui/schedules/{schedule_id}/toggle")
def toggle_schedule_ui(schedule_id: str, agent_id: str = Form(...), session: Session = Depends(get_session)):
    schedule = session.get(Schedule, schedule_id)
    if schedule is not None:
        update_schedule(session, schedule_id, enabled=not schedule.enabled)
    return RedirectResponse(url=f"/ui/agents/{agent_id}/schedules", status_code=303)
