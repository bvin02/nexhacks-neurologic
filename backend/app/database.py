"""
DecisionOS Database Configuration

SQLAlchemy async engine with SQLite for development.
Supports migration to PostgreSQL for production.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event
from .config import settings


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


# Create async engine with connection pooling settings for SQLite
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
    connect_args={
        "timeout": 30,  # Wait up to 30 seconds for locks
        "check_same_thread": False,
    },
)


# Enable foreign keys and WAL mode for SQLite
@event.listens_for(engine.sync_engine, "connect")
def configure_sqlite(dbapi_connection, connection_record):
    """Configure SQLite for better concurrency."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")  # Enable WAL for better concurrency
    cursor.execute("PRAGMA busy_timeout=30000")  # 30 second timeout for busy locks
    cursor.close()


# Session factory
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """Dependency to get database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
