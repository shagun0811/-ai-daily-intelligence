"""SQLAlchemy engine, session, and schema bootstrap."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config.logging import STAGE_DB, get_logger, log_stage
from app.config.settings import get_settings

logger = get_logger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


class Base(DeclarativeBase):
    """Declarative base for all aggregator models."""


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.resolved_database_url()
        connect_args = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(url, future=True, connect_args=connect_args)
        if url.startswith("sqlite"):
            _configure_sqlite(_engine)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )
    return _SessionLocal


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(*, seed: bool = True) -> None:
    """Create tables and optionally seed taxonomy + YAML sources."""
    # Import models so metadata is populated.
    from app.database import models as _models  # noqa: F401
    from app.database.seed import seed_database

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    log_stage(logger, STAGE_DB, "schema created url=%s", engine.url.render_as_string(hide_password=True))
    if seed:
        with session_scope() as session:
            seed_database(session)
        log_stage(logger, STAGE_DB, "seed complete")


def reset_engine() -> None:
    """Dispose the singleton engine. Used by tests."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
