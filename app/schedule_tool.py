"""`schedule_tool`：讓 agent 在對話中自己建立排程，對應 spec §7.3。

跟 skill 分開，是系統內建工具，所有 agent 都會掛載。刻意把 agent_id 綁在
closure 裡（不讓 model 自己傳 agent_id 參數）：spec 原本的函式簽章是
`create_schedule(agent_id, cron_expression, run_input=None)`，但若讓 model
自己填 agent_id，被誘導或幻覺打錯 id 時就會幫別的 agent 建排程；每次組
Agent 時我們已經知道正確的 agent_id 了，直接綁定比較安全。
"""

from __future__ import annotations

from pydantic_ai import RunContext
from pydantic_ai.toolsets import FunctionToolset
from sqlmodel import Session

from app.db import engine
from app.models import ScheduleCreatedBy
from app.schedule_service import ScheduleError
from app.schedule_service import create_schedule as _create_schedule


def build_schedule_toolset(agent_id: str) -> FunctionToolset:
    toolset = FunctionToolset(id="schedule-tool")

    @toolset.tool
    def create_schedule(_ctx: RunContext[None], cron_expression: str, run_input: str | None = None) -> str:
        """為目前這個 agent 建立一筆定時執行排程。

        使用時機：使用者在對話中要求「每天/每小時/固定時間幫我跑一次」之類的
        排程需求時呼叫，不需要使用者自己跳去排程管理頁面手動填表單。

        Args:
            cron_expression: 標準 5 欄位 cron 運算式，例如 "0 9 * * *" 代表每天早上 9 點。
            run_input: 排程觸發時要餵給這個 agent 的輸入內容；不填則視為空字串。
        """
        with Session(engine) as session:
            try:
                schedule = _create_schedule(
                    session,
                    agent_id=agent_id,
                    cron_expression=cron_expression,
                    created_by=ScheduleCreatedBy.agent,
                    run_input=run_input,
                )
            except ScheduleError as exc:
                return f"建立排程失敗：{exc}"

        next_run = schedule.next_run_at.isoformat() if schedule.next_run_at else "無"
        return f"已建立排程 {schedule.id}（cron='{schedule.cron_expression}'），下次執行時間：{next_run}"

    return toolset
