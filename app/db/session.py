from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base

engine: AsyncEngine = create_async_engine(settings.db_url, echo=False)

SessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


async def _get_columns(conn, table_name: str) -> set[str]:
    rows = (await conn.execute(text(f"PRAGMA table_info({table_name});"))).fetchall()
    return {r[1] for r in rows}


async def _ensure_column(conn, table: str, col: str, sql_type: str) -> None:
    cols = await _get_columns(conn, table)
    if col not in cols:
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {sql_type};"))


async def init_db() -> None:
    # важно: импортируем модели, чтобы Base.metadata знала о таблицах
    from app.db import models  # noqa: F401
    from app.db.seed import seed_canonical_attributes

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # users
        await _ensure_column(conn, "users", "gender", "VARCHAR(10)")

        # profiles — добавляем колонки, если база старая
        await _ensure_column(conn, "profiles", "name", "VARCHAR(64)")
        await _ensure_column(conn, "profiles", "age", "VARCHAR(10)")
        await _ensure_column(conn, "profiles", "nationality", "VARCHAR(64)")
        await _ensure_column(conn, "profiles", "city", "VARCHAR(128)")
        await _ensure_column(conn, "profiles", "marital_status", "VARCHAR(32)")
        await _ensure_column(conn, "profiles", "children", "VARCHAR(32)")
        await _ensure_column(conn, "profiles", "prayer", "VARCHAR(32)")
        await _ensure_column(conn, "profiles", "relocation", "VARCHAR(32)")
        await _ensure_column(conn, "profiles", "goal", "VARCHAR(32)")
        await _ensure_column(conn, "profiles", "extra_about", "TEXT")
        await _ensure_column(conn, "profiles", "aqida", "VARCHAR(32)")
        await _ensure_column(conn, "profiles", "polygyny", "VARCHAR(32)")

        await _ensure_column(conn, "profiles", "partner_age", "VARCHAR(32)")
        await _ensure_column(conn, "profiles", "partner_nationality_pref", "VARCHAR(64)")
        await _ensure_column(conn, "profiles", "partner_priority", "VARCHAR(64)")

        await _ensure_column(conn, "profiles", "about_me_text", "TEXT")
        await _ensure_column(conn, "profiles", "looking_for_text", "TEXT")

    async with SessionFactory() as session:
        await seed_canonical_attributes(session)
