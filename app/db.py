"""Database engine + session helpers (SQLite via SQLModel)."""

from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.config import get_config

_config = get_config()

# check_same_thread=False: FastAPI may touch the connection from worker threads.
engine = create_engine(
    _config.database_url,
    connect_args={"check_same_thread": False},
)


def _ensure_column(target_engine, table: str, column: str, ddl: str) -> None:
    """Idempotent ALTER TABLE guard: create_all never adds columns to existing tables."""
    with target_engine.connect() as conn:
        cols = [row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")]
        if not cols:
            return  # table doesn't exist yet; create_all will build it complete
        if column not in cols:
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            conn.commit()


def init_db() -> None:
    """Create tables. Import models for side-effect registration first."""
    from app import models  # noqa: F401  (registers tables on SQLModel.metadata)

    SQLModel.metadata.create_all(engine)
    # Slice C: pre-existing DBs have artifacts without review_status.
    _ensure_column(engine, "artifacts", "review_status", "VARCHAR DEFAULT 'draft'")
    # Relationship models: pre-existing DBs lack these FK columns.
    _ensure_column(engine, "opportunities", "company_id", "VARCHAR")
    _ensure_column(engine, "opportunities", "source_id", "VARCHAR")
    _ensure_column(engine, "contacts", "company_id", "VARCHAR")


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a DB session."""
    with Session(engine) as session:
        yield session
