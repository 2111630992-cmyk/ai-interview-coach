"""数据库引擎与会话。

- 开发默认 SQLite(async)，生产切 PostgreSQL(asyncpg) 只需改 DATABASE_URL。
- SQLModel 的 AsyncSession 让 async 路由里可以直接 `await session.exec(...)`。
"""

from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings

# SQLite 在多线程场景下的连接参数
_connect_args: dict = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
    connect_args=_connect_args,
)


# SQLite 默认不强制外键约束，显式打开，避免脏数据
if settings.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_fk(dbapi_conn, _record):  # pragma: no cover - 引擎层钩子
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：每个请求一个会话，异常时回滚。"""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """开发环境自动建表。

    生产环境请改用 Alembic 迁移（见 README「后续规划」与 requirements 注释）。
    """
    # 确保所有模型都已注册到 metadata
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def dispose_db() -> None:
    await engine.dispose()
