"""排程建立/計算共用邏輯，供人工設定（routers/schedules.py）與
Agent 自建（schedule_tool.py）共用，對應 spec §7。"""

from __future__ import annotations

from datetime import datetime, timezone

from croniter import CroniterBadCronError, croniter
from sqlmodel import Session, func, select

from app.config import settings
from app.models import Agent, Schedule, ScheduleCreatedBy


class ScheduleError(Exception):
    pass


def compute_next_run_at(cron_expression: str, base: datetime | None = None) -> datetime:
    base = base or datetime.now(timezone.utc)
    try:
        itr = croniter(cron_expression, base)
        return itr.get_next(datetime)
    except (CroniterBadCronError, ValueError) as exc:
        raise ScheduleError(f"cron 運算式不合法: {cron_expression} ({exc})") from exc


def create_schedule(
    session: Session,
    *,
    agent_id: str,
    cron_expression: str,
    created_by: ScheduleCreatedBy,
    run_input: str | None = None,
    enabled: bool = True,
) -> Schedule:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise ScheduleError(f"找不到 agent_id={agent_id}")

    if created_by == ScheduleCreatedBy.agent:
        # 數量軟上限，避免被誘導狂建排程（spec §8）。
        count = session.exec(
            select(func.count()).select_from(Schedule).where(
                Schedule.agent_id == agent_id,
                Schedule.created_by == ScheduleCreatedBy.agent,
                Schedule.reviewed_at == None,  # noqa: E711
            )
        ).one()
        if count >= settings.max_schedules_per_agent:
            raise ScheduleError(
                f"這個 agent 自己建立、還沒人工核准的排程已達上限（{settings.max_schedules_per_agent} 筆），"
                "請先到排程頁核准或刪掉一些再新增。"
            )
        # Agent 自建的排程一律先進「待審核」狀態，不會自動開始執行——呼應
        # spec §8「要求 agent 建立的排程預設 enabled=false 待人工核准」。
        # next_run_at 因此也是 None，在人工按下核准之前不可能被排程器挑到。
        enabled = False
        reviewed_at = None
    else:
        # 使用者自己在頁面上填的排程不需要審核，視為建立當下就已核准。
        reviewed_at = datetime.now(timezone.utc)

    next_run_at = compute_next_run_at(cron_expression) if enabled else None

    schedule = Schedule(
        agent_id=agent_id,
        cron_expression=cron_expression,
        enabled=enabled,
        created_by=created_by,
        run_input=run_input,
        next_run_at=next_run_at,
        reviewed_at=reviewed_at,
    )
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    return schedule


def list_schedules(session: Session, agent_id: str) -> list[Schedule]:
    return list(
        session.exec(
            select(Schedule).where(Schedule.agent_id == agent_id).order_by(Schedule.created_at.desc())
        )
    )


def list_all_schedules(session: Session) -> list[tuple[Schedule, Agent]]:
    """跨所有 agent 的排程清單，配對出建立它的 agent，給全域排程總覽頁用。"""
    rows = session.exec(
        select(Schedule, Agent)
        .join(Agent, Agent.id == Schedule.agent_id)
        .order_by(Schedule.created_at.desc())
    )
    return list(rows)


def is_pending_review(schedule: Schedule) -> bool:
    return schedule.created_by == ScheduleCreatedBy.agent and schedule.reviewed_at is None


def update_schedule(
    session: Session,
    schedule_id: str,
    *,
    enabled: bool | None = None,
    cron_expression: str | None = None,
    run_input: str | None = None,
) -> Schedule:
    schedule = session.get(Schedule, schedule_id)
    if schedule is None:
        raise ScheduleError(f"找不到 schedule_id={schedule_id}")

    if cron_expression is not None:
        schedule.cron_expression = cron_expression
    if run_input is not None:
        schedule.run_input = run_input
    if enabled is not None:
        schedule.enabled = enabled
        # 第一次從「待審核」被打開，等同人工核准；之後再暫停/恢復都不會
        # 重新回到待審核狀態。
        if enabled and schedule.reviewed_at is None:
            schedule.reviewed_at = datetime.now(timezone.utc)

    schedule.next_run_at = compute_next_run_at(schedule.cron_expression) if schedule.enabled else None

    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    return schedule


def due_schedules(session: Session, *, now: datetime | None = None) -> list[Schedule]:
    now = now or datetime.now(timezone.utc)
    return list(
        session.exec(
            select(Schedule).where(
                Schedule.enabled == True,  # noqa: E712
                Schedule.next_run_at != None,  # noqa: E711
                Schedule.next_run_at <= now,
            )
        )
    )
