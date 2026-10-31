import logging
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Append app to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import Base, get_database_url
import app.models  # load all models

config = context.config
database_url = get_database_url()

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

logger = logging.getLogger("alembic.env")


def run_migrations_offline() -> None:
    url = database_url.render_as_string(hide_password=False)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    url_string = database_url.render_as_string(hide_password=False)
    configuration["sqlalchemy.url"] = url_string

    # Inject a connection timeout for PostgreSQL/YugabyteDB backends so that
    # Alembic fails loudly and quickly when the database is unreachable instead
    # of hanging indefinitely.
    connect_args: dict = {}
    if url_string.startswith("postgresql") or url_string.startswith("postgres"):
        connect_args["connect_timeout"] = 10

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection, target_metadata=target_metadata
            )

            with context.begin_transaction():
                context.run_migrations()
    except Exception as exc:
        logger.error(
            "Failed to connect to the database while running migrations: %s",
            exc,
        )
        raise


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
