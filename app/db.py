from __future__ import annotations

from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)


def init_db() -> None:
    # 沿用現有 DB 時可移除這行改用既有的 migration 機制；POC 階段直接 create_all。
    import app.models  # noqa: F401  (register table models before create_all)

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
