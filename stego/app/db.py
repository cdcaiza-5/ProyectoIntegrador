"""Motor y sesiones de SQLAlchemy 2 sobre psycopg 3 (async)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger("stego.db")


class Base(DeclarativeBase):
    pass


class Database:
    """Envoltorio mínimo: engine + fábrica de sesiones + comprobación inicial."""

    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(
            url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            pool_recycle=1800,
            echo=False,
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False, autoflush=False)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as session:
            yield session

    async def check(self) -> bool:
        """Comprueba conexión y presencia de la tabla; nunca lanza la excepción."""
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
                table = await connection.scalar(text("SELECT to_regclass('stego.analyses')"))
        except Exception as exc:  # noqa: BLE001 - el arranque debe sobrevivir
            logger.error(
                "database_unavailable",
                extra={"fields": {"error_type": type(exc).__name__, "error_message": str(exc)}},
            )
            return False
        if table is None:
            logger.warning(
                "database_table_missing",
                extra={"fields": {"table": "stego.analyses", "hint": "aplicar db/stego/001_init.sql"}},
            )
            return False
        logger.info("database_ready", extra={"fields": {"table": "stego.analyses"}})
        return True

    async def dispose(self) -> None:
        await self.engine.dispose()
