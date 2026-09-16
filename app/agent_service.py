"""建立與執行 Agent，對應 spec §6。"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic_ai import Agent as PydanticAgent
from pydantic_ai.models import Model
from pydantic_ai_skills import SkillsToolset
from sqlmodel import Session

from app.config import settings
from app.models import Agent as AgentConfig
from app.models import RunLog, Skill
from app.schedule_tool import build_schedule_toolset
from app.skills_service import get_skills_by_ids


def _resolve_model(model_name: str) -> str | Model:
    """把 Agent 設定裡的 model 字串轉成 pydantic-ai 的 model。

    "openai:xxx" 形式的 model，"xxx" 在 Azure OpenAI 底下其實是 deployment
    name（不是底層模型名）。優先順序：
    1. 設定了 AZURE_OPENAI_ENDPOINT -> 走 AzureProvider
    2. 設定了 OPENAI_BASE_URL（例如 LiteLLM gateway）-> 走一般 OpenAIProvider
    3. 都沒設 -> 原字串交給 pydantic-ai 自行解析（含 anthropic: / google: 等其他前綴）
    """
    if not model_name.startswith("openai:"):
        return model_name
    bare_name = model_name.split(":", 1)[1]

    if settings.azure_openai_endpoint:
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.azure import AzureProvider

        provider = AzureProvider(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
        )
        return OpenAIChatModel(bare_name, provider=provider)

    if settings.openai_base_url:
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        provider = OpenAIProvider(base_url=settings.openai_base_url, api_key=settings.openai_api_key)
        return OpenAIChatModel(bare_name, provider=provider)

    return model_name


def build_agent(agent_config: AgentConfig, skills: list[Skill]) -> PydanticAgent:
    skill_dirs = [s.path for s in skills]
    skills_toolset = SkillsToolset(directories=skill_dirs)
    schedule_toolset = build_schedule_toolset(agent_config.id)

    return PydanticAgent(
        model=_resolve_model(agent_config.model),
        instructions=agent_config.instructions or None,
        toolsets=[skills_toolset, schedule_toolset],
    )


async def run_agent_once(
    session: Session,
    agent_config: AgentConfig,
    *,
    run_input: str,
    triggered_by: str = "user",
    schedule_id: str | None = None,
) -> RunLog:
    skills = get_skills_by_ids(session, agent_config.skill_ids)
    log = RunLog(
        agent_id=agent_config.id,
        schedule_id=schedule_id,
        triggered_by=triggered_by,
        input_text=run_input,
    )

    try:
        agent = build_agent(agent_config, skills)
        result = await agent.run(run_input)
        log.output_text = str(result.output)
    except Exception as exc:  # POC：直接把例外訊息記下來給前端看，不特別分類
        log.error_text = f"{type(exc).__name__}: {exc}"

    log.finished_at = datetime.now(timezone.utc)
    session.add(log)
    session.commit()
    session.refresh(log)
    return log
