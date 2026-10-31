import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.core import database


def _temporary_sqlite_fallback(tmp_path):
    fallback_url = make_url(f"sqlite:///{tmp_path / 'fallback.db'}")
    fallback_engine = create_engine(
        fallback_url,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    database._configure_sqlite(fallback_engine)
    with fallback_engine.connect():
        pass
    return fallback_engine, fallback_url


def test_yugabyte_startup_failure_activates_working_sqlite_fallback(monkeypatch, tmp_path):
    previous_engine = database.engine
    previous_url = database.database_url
    previous_yugabyte_state = database.is_live_yugabyte
    real_create_engine = database.create_engine
    fallback_engine = None

    def create_engine_with_unreachable_yugabyte(url, *args, **kwargs):
        if url.get_backend_name() == "postgresql":
            raise OperationalError("connect", {}, OSError("database unavailable"))
        return real_create_engine(url, *args, **kwargs)

    try:
        monkeypatch.setattr(database, "engine", None)
        monkeypatch.setattr(database, "database_url", None)
        monkeypatch.setattr(database, "is_live_yugabyte", False)
        monkeypatch.setattr(
            database,
            "get_database_url",
            lambda: make_url("postgresql+psycopg2://user:password@unreachable.invalid:5433/mediflow"),
        )
        monkeypatch.setattr(database, "create_engine", create_engine_with_unreachable_yugabyte)
        monkeypatch.setattr(
            database,
            "_create_sqlite_engine",
            lambda: _temporary_sqlite_fallback(tmp_path),
        )
        monkeypatch.setattr(database.settings, "APP_ENV", "development")
        monkeypatch.setattr(database.settings, "DB_SQLITE_FALLBACK", True)
        database.SessionLocal.configure(bind=None)

        fallback_engine = database.initialize_database()

        assert fallback_engine.dialect.name == "sqlite"
        assert not database.is_yugabyte_active()
        with database.SessionLocal() as session:
            assert session.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        if fallback_engine is not None:
            fallback_engine.dispose()
        database.engine = previous_engine
        database.database_url = previous_url
        database.is_live_yugabyte = previous_yugabyte_state
        database.SessionLocal.configure(bind=previous_engine)


def test_runtime_yugabyte_connection_failure_switches_future_sessions_to_sqlite(monkeypatch, tmp_path):
    previous_engine = database.engine
    previous_url = database.database_url
    previous_yugabyte_state = database.is_live_yugabyte
    remote_engine = create_engine("sqlite://")

    try:
        monkeypatch.setattr(database.settings, "APP_ENV", "development")
        monkeypatch.setattr(database.settings, "DB_SQLITE_FALLBACK", True)
        monkeypatch.setattr(
            database,
            "_create_sqlite_engine",
            lambda: _temporary_sqlite_fallback(tmp_path),
        )
        database._bind_engine(
            remote_engine,
            make_url("postgresql+psycopg2://user:password@cluster.invalid:5433/mediflow"),
            yugabyte=True,
        )

        switched = database.fallback_to_sqlite(
            OperationalError("query", {}, OSError("connection exhausted"))
        )

        assert switched
        assert not database.is_yugabyte_active()
        assert database.get_engine().dialect.name == "sqlite"
        assert inspect(database.get_engine()).has_table("organisations")
        with database.SessionLocal() as session:
            assert session.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        if database.engine is not None and database.engine is not remote_engine:
            database.engine.dispose()
        remote_engine.dispose()
        database.engine = previous_engine
        database.database_url = previous_url
        database.is_live_yugabyte = previous_yugabyte_state
        database.SessionLocal.configure(bind=previous_engine)


def test_yugabyte_pool_exhaustion_triggers_sqlite_failover(monkeypatch, tmp_path):
    previous_engine = database.engine
    previous_url = database.database_url
    previous_yugabyte_state = database.is_live_yugabyte
    remote_engine = create_engine(
        "sqlite://",
        poolclass=database._YugabyteQueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.01,
    )
    checked_out_connection = None

    try:
        monkeypatch.setattr(database.settings, "APP_ENV", "development")
        monkeypatch.setattr(database.settings, "DB_SQLITE_FALLBACK", True)
        monkeypatch.setattr(
            database,
            "_create_sqlite_engine",
            lambda: _temporary_sqlite_fallback(tmp_path),
        )
        database._bind_engine(
            remote_engine,
            make_url("postgresql+psycopg2://user:password@cluster.invalid:5433/mediflow"),
            yugabyte=True,
        )
        checked_out_connection = remote_engine.connect()

        with pytest.raises(SQLAlchemyTimeoutError):
            remote_engine.connect()

        assert not database.is_yugabyte_active()
        assert database.get_engine().dialect.name == "sqlite"
    finally:
        if checked_out_connection is not None:
            checked_out_connection.close()
        if database.engine is not None and database.engine is not remote_engine:
            database.engine.dispose()
        remote_engine.dispose()
        database.engine = previous_engine
        database.database_url = previous_url
        database.is_live_yugabyte = previous_yugabyte_state
        database.SessionLocal.configure(bind=previous_engine)


def test_yugabyte_pool_configuration_enforces_three_connections_per_process(monkeypatch):
    previous_engine = database.engine
    previous_url = database.database_url
    previous_yugabyte_state = database.is_live_yugabyte
    real_create_engine = database.create_engine
    captured_options = {}
    candidate_engine = None

    def create_mock_yugabyte_engine(url, *args, **kwargs):
        nonlocal candidate_engine
        if url.get_backend_name() == "postgresql":
            captured_options.update(kwargs)
            candidate_engine = real_create_engine("sqlite://")
            return candidate_engine
        return real_create_engine(url, *args, **kwargs)

    try:
        monkeypatch.setattr(database, "engine", None)
        monkeypatch.setattr(database, "database_url", None)
        monkeypatch.setattr(database, "is_live_yugabyte", False)
        monkeypatch.setattr(
            database,
            "get_database_url",
            lambda: make_url("postgresql+psycopg2://user:password@cluster.invalid:5433/mediflow"),
        )
        monkeypatch.setattr(database, "create_engine", create_mock_yugabyte_engine)
        database.SessionLocal.configure(bind=None)

        assert database.initialize_database() is candidate_engine
        assert database.is_yugabyte_active()
        assert captured_options["pool_size"] == 2
        assert captured_options["max_overflow"] == 1
        assert captured_options["pool_timeout"] == 10
        assert captured_options["pool_recycle"] == 900
        assert captured_options["pool_pre_ping"] is True
        assert captured_options["connect_args"]["connect_timeout"] == 5
    finally:
        if candidate_engine is not None:
            candidate_engine.dispose()
        database.engine = previous_engine
        database.database_url = previous_url
        database.is_live_yugabyte = previous_yugabyte_state
        database.SessionLocal.configure(bind=previous_engine)


def test_production_fails_closed_when_yugabyte_is_unavailable(monkeypatch):
    previous_engine = database.engine
    previous_url = database.database_url
    previous_yugabyte_state = database.is_live_yugabyte

    def fail_yugabyte_connection(url, *args, **kwargs):
        raise OperationalError("connect", {}, OSError("database unavailable"))

    try:
        monkeypatch.setattr(database, "engine", None)
        monkeypatch.setattr(database, "database_url", None)
        monkeypatch.setattr(database, "is_live_yugabyte", False)
        monkeypatch.setattr(
            database,
            "get_database_url",
            lambda: make_url("postgresql+psycopg2://user:password@unreachable.invalid:5433/mediflow"),
        )
        monkeypatch.setattr(database, "create_engine", fail_yugabyte_connection)
        monkeypatch.setattr(database.settings, "APP_ENV", "production")
        monkeypatch.setattr(database.settings, "DB_SQLITE_FALLBACK", None)
        database.SessionLocal.configure(bind=None)

        with pytest.raises(RuntimeError, match="DB_SQLITE_FALLBACK is disabled"):
            database.initialize_database()

        assert database.engine is None
    finally:
        database.engine = previous_engine
        database.database_url = previous_url
        database.is_live_yugabyte = previous_yugabyte_state
        database.SessionLocal.configure(bind=previous_engine)
