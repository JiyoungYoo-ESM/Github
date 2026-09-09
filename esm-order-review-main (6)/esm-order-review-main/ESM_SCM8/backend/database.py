"""SQLAlchemy database wiring for persistent application data."""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


def normalize_database_url(url: str) -> str:
    """Use psycopg 3 for Railway-style PostgreSQL URLs."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL이 설정되지 않았습니다.")
    url = normalize_database_url(DATABASE_URL)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db_session() -> Generator[Session, None, None]:
    try:
        factory = get_session_factory()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="문의 저장소가 아직 연결되지 않았습니다. 관리자에게 문의해 주세요.",
        ) from exc
    with factory() as session:
        yield session
