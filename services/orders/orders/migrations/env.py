"""Подготовка окружения для миграций.

Миграция — это записанное изменение структуры базы данных. Каждое такое
изменение лежит отдельным файлом в migrations/versions и применяется
командой `alembic upgrade head`.
"""

from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

from orders import models  # noqa: F401  нужен, чтобы таблицы попали в Base.metadata
from orders.config import settings
from orders.db import Base

config = context.config
# ConfigParser обрабатывает знак % в паролях и путях как начало подстановки.
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

if config.config_file_name is not None:
    logging_config = (
        config.config_file_name
        if config.file_config.has_section("loggers")
        else Path(__file__).with_name("alembic.ini")
    )
    fileConfig(logging_config)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
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
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
