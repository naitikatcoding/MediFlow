import logging
import threading
import urllib.parse
from typing import Generator, Optional

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.exc import (
    DBAPIError,
    DisconnectionError,
    InterfaceError,
    OperationalError,
    TimeoutError as SQLAlchemyTimeoutError,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.config import settings

logger = logging.getLogger("mediflow.database")

_engine_lock = threading.RLock()
engine: Optional[Engine] = None
database_url: Optional[URL] = None
primary_database_url: Optional[URL] = None
is_live_yugabyte = False
_retired_engines: list[Engine] = []
_failback_retry_interval_seconds = 10
_failback_stop_event = threading.Event()
_failback_monitor_thread: Optional[threading.Thread] = None

SessionLocal = sessionmaker(autocommit=False, autoflush=False)
Base = declarative_base()


class _YugabyteQueuePool(QueuePool):
    def _do_get(self):
        try:
            return super()._do_get()
        except (
            OperationalError,
            InterfaceError,
            DisconnectionError,
            SQLAlchemyTimeoutError,
        ) as exc:
            fallback_to_sqlite(exc)
            raise


def sanitize_database_url(raw_url: str) -> str:
    """Percent-encode Windows certificate paths in PostgreSQL DSNs."""
    if "sslrootcert=" in raw_url:
        prefix, _, cert_part = raw_url.partition("sslrootcert=")
        cert_path, other_sep, rest = cert_part.partition("&")
        if " " in cert_path or "\\" in cert_path:
            normalized_path = cert_path.replace("\\", "/")
            encoded_path = urllib.parse.quote(normalized_path, safe=":/")
            raw_url = f"{prefix}sslrootcert={encoded_path}{other_sep}{rest}"
    return raw_url


def get_database_url() -> URL:
    import os
    if os.environ.get("PYTEST_CURRENT_TEST") or settings.APP_ENV.lower() == "test":
        test_url = os.environ.get("DATABASE_URL")
        if test_url and ("sqlite" in test_url):
            return make_url(test_url)
        return make_url("sqlite:///./test_app.db")
    url = make_url(sanitize_database_url(settings.DATABASE_URL))
    if url.drivername == "postgresql":
        return url.set(drivername="postgresql+psycopg2")
    return url


def _configure_sqlite(sqlite_engine: Engine) -> None:
    @event.listens_for(sqlite_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()


def _create_sqlite_engine() -> tuple[Engine, URL]:
    fallback_url = make_url("sqlite:///./mediflow.db")
    fallback_engine = create_engine(
        fallback_url,
        connect_args={"check_same_thread": False},
        echo=settings.DB_ECHO,
        pool_pre_ping=True,
    )
    _configure_sqlite(fallback_engine)
    with fallback_engine.connect():
        pass
    return fallback_engine, fallback_url


def _ensure_sqlite_schema(sqlite_engine: Engine) -> None:
    import app.models

    Base.metadata.create_all(bind=sqlite_engine)
    ensure_audit_correlation_schema(sqlite_engine)


def ensure_audit_correlation_schema(active_engine: Engine) -> None:
    from app.models.audit import AuditEvent

    inspector = inspect(active_engine)
    if not inspector.has_table(AuditEvent.__tablename__):
        raise RuntimeError("The audit_events table is missing after schema creation.")

    columns = {
        column["name"] for column in inspector.get_columns(AuditEvent.__tablename__)
    }
    if "correlation_id" not in columns:
        with active_engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE audit_events ADD COLUMN correlation_id VARCHAR(64)"
            )

    correlation_index = next(
        (
            index
            for index in AuditEvent.__table__.indexes
            if index.name == "ix_audit_correlation"
        ),
        None,
    )
    if correlation_index is None:
        raise RuntimeError("The audit correlation index is missing from the model.")
    correlation_index.create(bind=active_engine, checkfirst=True)


def _bind_engine(active_engine: Engine, active_url: URL, yugabyte: bool) -> None:
    global engine, database_url, is_live_yugabyte, primary_database_url
    engine = active_engine
    database_url = active_url
    is_live_yugabyte = yugabyte
    if yugabyte:
        primary_database_url = active_url
    SessionLocal.configure(bind=active_engine)
    if yugabyte:
        @event.listens_for(active_engine, "handle_error")
        def switch_after_connection_error(exception_context):
            error = exception_context.sqlalchemy_exception or exception_context.original_exception
            fallback_to_sqlite(error)


def _create_yugabyte_engine(primary_url: URL) -> Engine:
    return create_engine(
        primary_url,
        connect_args={"connect_timeout": 5},
        echo=settings.DB_ECHO,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=10,
        pool_recycle=900,
        pool_pre_ping=True,
        pool_use_lifo=True,
        poolclass=_YugabyteQueuePool,
    )


def _try_restore_yugabyte() -> bool:
    """Rebind future sessions to Yugabyte when its configured endpoint recovers."""
    global engine

    with _engine_lock:
        if is_live_yugabyte or not settings.is_yugabyte:
            return is_live_yugabyte

        primary_url = primary_database_url or get_database_url()
        if primary_url.get_backend_name() != "postgresql":
            logger.error(
                "Automatic Yugabyte recovery is disabled because the configured "
                "database URL is not PostgreSQL."
            )
            return False

        candidate_engine: Optional[Engine] = None
        try:
            candidate_engine = _create_yugabyte_engine(primary_url)
            with candidate_engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:
            if candidate_engine is not None:
                candidate_engine.dispose()
            logger.debug(
                "Yugabyte recovery probe failed (%s); SQLite remains active.",
                type(exc).__name__,
            )
            return False

        fallback_engine = engine
        _bind_engine(candidate_engine, primary_url, yugabyte=True)
        if fallback_engine is not None:
            _retired_engines.append(fallback_engine)
        logger.warning(
            "YugabyteDB connection restored; new sessions now use YugabyteDB. "
            "Changes made in the local SQLite fallback remain local and are not "
            "automatically copied."
        )
        return True


def _run_failback_monitor() -> None:
    while not _failback_stop_event.is_set():
        if not is_yugabyte_active():
            try:
                _try_restore_yugabyte()
            except Exception:
                logger.exception(
                    "Unexpected error while checking whether YugabyteDB has recovered."
                )
        if _failback_stop_event.wait(_failback_retry_interval_seconds):
            return


def _start_failback_monitor() -> None:
    global _failback_monitor_thread

    if not settings.is_yugabyte:
        return

    with _engine_lock:
        if _failback_monitor_thread is not None and _failback_monitor_thread.is_alive():
            return
        _failback_stop_event.clear()
        _failback_monitor_thread = threading.Thread(
            target=_run_failback_monitor,
            name="mediflow-yugabyte-failback",
            daemon=True,
        )
        _failback_monitor_thread.start()


def _stop_failback_monitor() -> None:
    global _failback_monitor_thread

    _failback_stop_event.set()
    monitor_thread = _failback_monitor_thread
    if monitor_thread is not None and monitor_thread is not threading.current_thread():
        monitor_thread.join(timeout=10)
    _failback_monitor_thread = None


def _fallback_or_raise(error: Exception, failed_engine: Optional[Engine] = None) -> None:
    if failed_engine is not None:
        failed_engine.dispose()
    if not settings.allow_sqlite_fallback:
        logger.error(
            "YugabyteDB connection failed and SQLite fallback is disabled; "
            "APP_ENV=production fails closed (%s).",
            type(error).__name__,
        )
        raise RuntimeError(
            "YugabyteDB is unavailable and DB_SQLITE_FALLBACK is disabled."
        ) from error

    logger.warning(
        "YugabyteDB connection failed (%s); switching this process to local SQLite fallback.",
        type(error).__name__,
    )
    try:
        fallback_engine, fallback_url = _create_sqlite_engine()
    except Exception:
        logger.exception("Could not initialize the SQLite fallback database.")
        raise
    _bind_engine(fallback_engine, fallback_url, yugabyte=False)
    try:
        _ensure_sqlite_schema(fallback_engine)
    except Exception:
        fallback_engine.dispose()
        logger.exception("Could not initialize the SQLite fallback schema.")
        raise
    logger.warning("Active database: local SQLite fallback (mediflow.db).")
    _start_failback_monitor()


def initialize_database() -> Engine:
    """Initialize one bounded engine per application process, after worker startup."""
    global engine
    with _engine_lock:
        if engine is not None:
            return engine

        try:
            primary_url = get_database_url()
        except Exception as exc:
            if settings.is_yugabyte:
                _fallback_or_raise(exc)
                assert engine is not None
                return engine
            raise

        if primary_url.get_backend_name() != "postgresql":
            sqlite_engine = create_engine(
                primary_url,
                connect_args={"check_same_thread": False},
                echo=settings.DB_ECHO,
                pool_pre_ping=True,
            )
            _configure_sqlite(sqlite_engine)
            with sqlite_engine.connect():
                pass
            _bind_engine(sqlite_engine, primary_url, yugabyte=False)
            logger.info("Active database: SQLite (%s).", primary_url.database or "configured file")
            return sqlite_engine

        candidate_engine: Optional[Engine] = None
        try:
            candidate_engine = _create_yugabyte_engine(primary_url)
            with candidate_engine.connect():
                pass
        except Exception as exc:
            _fallback_or_raise(exc, candidate_engine)
            assert engine is not None
            return engine

        _bind_engine(candidate_engine, primary_url, yugabyte=True)
        max_connections = settings.DB_POOL_SIZE + settings.DB_MAX_OVERFLOW
        logger.info(
            "Active database: YugabyteDB/PostgreSQL; per-process pool limit=%s "
            "(pool_size=%s, max_overflow=%s).",
            max_connections,
            settings.DB_POOL_SIZE,
            settings.DB_MAX_OVERFLOW,
        )
        return candidate_engine


def get_engine() -> Engine:
    active_engine = initialize_database()
    return active_engine


def is_yugabyte_active() -> bool:
    return is_live_yugabyte


def is_connection_failure(error: Exception) -> bool:
    return isinstance(
        error,
        (
            OperationalError,
            InterfaceError,
            DisconnectionError,
            SQLAlchemyTimeoutError,
        ),
    ) or (isinstance(error, DBAPIError) and error.connection_invalidated)


def fallback_to_sqlite(error: Exception) -> bool:
    """Switch future sessions to SQLite after a live YSQL connection failure."""
    global engine
    if not is_connection_failure(error):
        return False

    with _engine_lock:
        if not is_live_yugabyte:
            return False
        if not settings.allow_sqlite_fallback:
            logger.error(
                "YugabyteDB connection failure (%s); production fallback is disabled.",
                type(error).__name__,
            )
            return False

        failed_engine = engine
        try:
            fallback_engine, fallback_url = _create_sqlite_engine()
        except Exception:
            logger.exception("Could not initialize the SQLite fallback database.")
            raise
        _bind_engine(fallback_engine, fallback_url, yugabyte=False)
        try:
            _ensure_sqlite_schema(fallback_engine)
        except Exception:
            fallback_engine.dispose()
            logger.exception("Could not initialize the SQLite fallback schema.")
            raise
        if failed_engine is not None:
            failed_engine.dispose()
        logger.error(
            "YugabyteDB connection failed (%s); future requests will use local SQLite "
            "(mediflow.db). The failed request is not retried.",
            type(error).__name__,
        )
        _start_failback_monitor()
        return True


def dispose_engine() -> None:
    _stop_failback_monitor()
    with _engine_lock:
        if engine is not None:
            engine.dispose()
            logger.info("Database connection pool disposed.")
        for retired_engine in _retired_engines:
            retired_engine.dispose()
        _retired_engines.clear()


def get_db() -> Generator[Session, None, None]:
    initialize_database()
    db = SessionLocal()
    try:
        yield db
    except Exception as exc:
        fallback_to_sqlite(exc)
        raise
    finally:
        db.close()
