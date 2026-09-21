from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine

from .config import DATABASE_URL


engine_options = {"connect_args": {"check_same_thread": False}} if DATABASE_URL.startswith("sqlite") else {"pool_pre_ping": True}
engine = create_engine(DATABASE_URL, **engine_options)


def create_db_and_tables() -> None:
    """Convenient for fresh local/test SQLite databases; production uses Alembic."""
    if DATABASE_URL.startswith("sqlite"):
        SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
