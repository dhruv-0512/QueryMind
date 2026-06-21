from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

# Create SQLAlchemy Async Engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.LOG_LEVEL.upper() == "DEBUG",
    pool_size=10,
    max_overflow=20
)

# Create Session Factory
SessionLocal = async_sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession
)

# Base class for SQLAlchemy Models
class Base(DeclarativeBase):
    pass

# DB Dependency for FastAPI Routes
async def get_db():
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
