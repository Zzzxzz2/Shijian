"""Async database engine, session factory, WAL init, and retry decorator."""
import asyncio
from functools import wraps
from typing import Any, Callable, TypeVar

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import DATABASE_URL

_connect_args: dict[str, Any] = {}
# check_same_thread is SQLite-only; PostgreSQL rejects it
if "sqlite" in DATABASE_URL:
    _connect_args["check_same_thread"] = False

engine = create_async_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,
    echo=False,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

F = TypeVar("F", bound=Callable[..., Any])


def db_retry(max_retries: int = 3, base_delay: float = 0.1) -> Callable[[F], F]:
    """Decorator: retry failed write operations with exponential backoff.

    Catches SQLite *database is locked* errors and retries up to
    ``max_retries`` times with delay = base_delay * (2 ** attempt).
    Non-lock errors are re-raised immediately.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    msg = str(exc).lower()
                    if "database is locked" in msg or "locked" in msg:
                        last_exc = exc
                        if attempt < max_retries - 1:
                            await asyncio.sleep(base_delay * (2**attempt))
                    else:
                        raise
            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator


async def init_db() -> None:
    """Initialize database: set WAL mode + busy_timeout (SQLite only), create tables."""
    if "sqlite" in DATABASE_URL:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            await conn.exec_driver_sql("PRAGMA busy_timeout=5000")
            await conn.commit()

    # Late import avoids circular dependency
    from models import Base  # noqa: PLC0415

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Migration: add model column to api_keys if missing
    if "sqlite" in DATABASE_URL:
        async with engine.connect() as conn:
            result = await conn.exec_driver_sql(
                "PRAGMA table_info(api_keys)"
            )
            cols = {row[1] for row in result.fetchall()}
            if "model" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE api_keys ADD COLUMN model VARCHAR(100) DEFAULT ''"
                )
                await conn.commit()
            if "name" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE api_keys ADD COLUMN name VARCHAR(100) DEFAULT ''"
                )
                await conn.commit()

    # Migration: add auth_config column to projects if missing
    if "sqlite" in DATABASE_URL:
        async with engine.connect() as conn:
            result = await conn.exec_driver_sql(
                "PRAGMA table_info(projects)"
            )
            cols = {row[1] for row in result.fetchall()}
            if "auth_config" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE projects ADD COLUMN auth_config TEXT DEFAULT '{}'"
                )
                await conn.commit()
            if "ai_config" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE projects ADD COLUMN ai_config TEXT DEFAULT '{}'"
                )
                await conn.commit()
            if "notification_config" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE projects ADD COLUMN notification_config TEXT DEFAULT '{}'"
                )
                await conn.commit()

    # Migration: add source column to test_runs if missing
    if "sqlite" in DATABASE_URL:
        async with engine.connect() as conn:
            result = await conn.exec_driver_sql(
                "PRAGMA table_info(test_runs)"
            )
            cols = {row[1] for row in result.fetchall()}
            if "source" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE test_runs ADD COLUMN source VARCHAR(20) DEFAULT ''"
                )
                await conn.commit()

    # Migration: add skip_auth column to test_cases if missing
    if "sqlite" in DATABASE_URL:
        async with engine.connect() as conn:
            result = await conn.exec_driver_sql(
                "PRAGMA table_info(test_cases)"
            )
            cols = {row[1] for row in result.fetchall()}
            if "skip_auth" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE test_cases ADD COLUMN skip_auth BOOLEAN DEFAULT 0"
                )
                await conn.commit()

    # Migration: add tags column to test_cases if missing
    if "sqlite" in DATABASE_URL:
        async with engine.connect() as conn:
            result = await conn.exec_driver_sql(
                "PRAGMA table_info(test_cases)"
            )
            cols = {row[1] for row in result.fetchall()}
            if "tags" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE test_cases ADD COLUMN tags TEXT DEFAULT '[]'"
                )
                await conn.commit()

    # Migration: add email column to users if missing
    if "sqlite" in DATABASE_URL:
        async with engine.connect() as conn:
            result = await conn.exec_driver_sql(
                "PRAGMA table_info(users)"
            )
            cols = {row[1] for row in result.fetchall()}
            if "email" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN email VARCHAR(120) DEFAULT ''"
                )
                await conn.commit()
            if "verified" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN verified BOOLEAN DEFAULT 0"
                )
                await conn.commit()
            if "ip_address" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN ip_address VARCHAR(45) DEFAULT ''"
                )
                await conn.commit()

    # Migration: add token_version + notification_config to users if missing
    if "sqlite" in DATABASE_URL:
        async with engine.connect() as conn:
            result = await conn.exec_driver_sql(
                "PRAGMA table_info(users)"
            )
            cols = {row[1] for row in result.fetchall()}
            if "token_version" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 0"
                )
                await conn.commit()
            if "notification_config" not in cols:
                await conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN notification_config TEXT DEFAULT '{}'"
                )
                await conn.commit()

    # 方案A：startup SQL 迁移 — NULL → 0 双保险
    if "sqlite" in DATABASE_URL:
        async with engine.connect() as conn:
            await conn.exec_driver_sql(
                "UPDATE users SET token_version = 0 WHERE token_version IS NULL"
            )
            await conn.exec_driver_sql(
                "UPDATE users SET email = '' WHERE email IS NULL"
            )
            await conn.exec_driver_sql(
                "UPDATE users SET verified = 0 WHERE verified IS NULL"
            )
            await conn.exec_driver_sql(
                "UPDATE users SET ip_address = '' WHERE ip_address IS NULL"
            )
            await conn.commit()


async def get_db():
    """FastAPI dependency: yield an async database session."""
    async with async_session() as session:
        yield session
