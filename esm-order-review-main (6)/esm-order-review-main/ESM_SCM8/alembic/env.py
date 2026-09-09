from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.config import DATABASE_URL
from backend.database import Base, normalize_database_url
from backend.models import (  # noqa: F401
    AnalysisJob,
    AuthSession,
    LatestAnalysisSnapshot,
    SupportAttachment,
    SupportStatusEvent,
    SupportTicket,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL이 설정되지 않아 마이그레이션을 실행할 수 없습니다.")

config.set_main_option("sqlalchemy.url", normalize_database_url(DATABASE_URL).replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
