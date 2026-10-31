import logging
import urllib.parse
from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.core.config import settings

logger = logging.getLogger("mediflow.database")


def sanitize_database_url(raw_url: str) -> str:
    """Ensure Windows file paths with spaces in DSN queries (e.g. sslrootcert) are properly percent-encoded."""
    if "sslrootcert=" in raw_url:
        prefix, sep, cert_part = raw_url.partition("sslrootcert=")
        cert_path, other_sep, rest = cert_part.partition("&")
        if " " in cert_path or "\\" in cert_path:
            normalized_path = cert_path.replace("\\", "/")
            # percent encode spaces and special chars, keeping colons and slashes
            encoded_path = urllib.parse.quote(normalized_path, safe=":/")
            raw_url = f"{prefix}sslrootcert={encoded_path}{other_sep}{rest}"
    return raw_url


def get_database_url() -> URL:
    raw_url = sanitize_database_url(settings.DATABASE_URL)
    url = make_url(raw_url)
    if url.drivername == "postgresql":
        return url.set(drivername="postgresql+psycopg2")
    return url


def _configure_sqlite(eng):
    @event.listens_for(eng, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def create_resilient_engine():
    """
    Creates the SQLAlchemy engine for YugabyteDB / PostgreSQL.
    If the remote database is unreachable (e.g. network sandbox, offline, bad credentials),
    it transparently falls back to a local PostgreSQL-compatible SQLite database (mediflow.db).
    """
    primary_url = get_database_url()
    backend = primary_url.get_backend_name()
    
    if backend == "postgresql":
        try:
            candidate_engine = create_engine(
                primary_url,
                connect_args={"connect_timeout": 3},
                echo=settings.DB_ECHO,
                pool_pre_ping=True,
            )
            # Test connectivity immediately
            with candidate_engine.connect() as conn:
                logger.info("Successfully connected to operational database: YugabyteDB / PostgreSQL.")
            return candidate_engine, primary_url, True
        except Exception as e:
            logger.warning(
                f"YugabyteDB connection attempt failed ({e}). "
                "Honest fallback: operating in local PostgreSQL-compatible SQLite mode (mediflow.db)."
            )
            fallback_url = make_url("sqlite:///./mediflow.db")
            fallback_engine = create_engine(
                fallback_url,
                connect_args={"check_same_thread": False},
                echo=settings.DB_ECHO,
                pool_pre_ping=True,
            )
            _configure_sqlite(fallback_engine)
            return fallback_engine, fallback_url, False
    else:
        sqlite_engine = create_engine(
            primary_url,
            connect_args={"check_same_thread": False},
            echo=settings.DB_ECHO,
            pool_pre_ping=True,
        )
        _configure_sqlite(sqlite_engine)
        return sqlite_engine, primary_url, False


engine, database_url, is_live_yugabyte = create_resilient_engine()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
