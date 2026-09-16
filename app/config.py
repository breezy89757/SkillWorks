"""集中管理環境變數設定（沿用 .env，見 .env.example）。"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'app.db'}"
    skills_storage_dir: Path = BASE_DIR / "skills_storage"

    redis_url: str = "redis://localhost:6379/0"

    # Azure OpenAI（AOAI）。若有設定，"openai:<deployment-name>" 形式的
    # model 會走 AzureProvider，優先於下面的 openai_base_url。
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None

    # LiteLLM gateway（或任何其他 OpenAI-compatible endpoint）。POC 階段先
    # 開放使用者在建立 Agent 時自行輸入 model 名稱字串，實際能選哪些 model
    # 待與管理員確認（spec §9）。
    openai_base_url: str | None = None
    openai_api_key: str = "not-needed-for-litellm-gateway"
    default_model: str = "openai:gpt-4o-mini"

    # Agent 自建排程（schedule_tool）暫無審核機制，spec §8 已知風險；
    # 先加一個軟上限避免單一 Agent 被誘導狂建排程。
    max_schedules_per_agent: int = 20

    scheduler_poll_interval_seconds: int = 30

    # "inprocess"：FastAPI process 自己跑 asyncio 迴圈輪詢 DB，不需要
    #   Redis/Celery，適合本機/POC 測試（見 app/inprocess_scheduler.py）。
    # "celery"：照 spec §7.1 用 Celery beat + worker（見 worker/）。
    # "off"：都不跑，排程只會被記錄，不會自動執行。
    # 兩種 backend 不要同時開，否則同一筆排程可能被跑兩次。
    scheduler_backend: str = "inprocess"


settings = Settings()
settings.skills_storage_dir.mkdir(parents=True, exist_ok=True)
(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
