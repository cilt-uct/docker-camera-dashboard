from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator

Base = declarative_base()

def create_db(settings):
    """Create engine and session factory from settings"""

    engine = create_async_engine(
        settings.DATABASE_URL,
        # echo=settings.SERVER_DEBUG,
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
    )

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    return engine, session_factory

async def get_db(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            # Rollback the session in case of an exception to avoid leaving the session in a bad state
            await session.rollback()
            raise
