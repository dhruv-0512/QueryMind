import pytest
import asyncio
from sqlalchemy import text
from app.config import settings, Settings
from app.database import engine, SessionLocal
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

def test_database_url_sanitization():
    # Test raw URL with ?sslmode=require
    raw_url = "postgresql+asyncpg://user:pass@ep-test.us-east-2.aws.neon.tech/neondb?sslmode=require"
    s = Settings(
        DATABASE_URL=raw_url,
        REDIS_URL="redis://localhost:6379",
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        CHROMADB_HOST="localhost",
        CHROMADB_PORT=8000,
        JWT_SECRET_KEY="secret"
    )
    assert "sslmode" not in s.DATABASE_URL
    assert s.DATABASE_URL == "postgresql+asyncpg://user:pass@ep-test.us-east-2.aws.neon.tech/neondb"
    assert s.DB_CONNECT_ARGS == {"ssl": "require"}

def test_local_database_url_sanitization():
    raw_url = "postgresql+asyncpg://platform_user:platform_password@localhost:5432/platform_db"
    s = Settings(
        DATABASE_URL=raw_url,
        REDIS_URL="redis://localhost:6379",
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        CHROMADB_HOST="localhost",
        CHROMADB_PORT=8000,
        JWT_SECRET_KEY="secret"
    )
    assert s.DATABASE_URL == raw_url
    assert s.DB_CONNECT_ARGS == {}

@pytest.mark.asyncio
async def test_async_engine_neon_connection():
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT 1"))
            val = res.scalar()
            assert val == 1
    finally:
        await engine.dispose()

@pytest.mark.asyncio
async def test_session_local_query():
    try:
        async with SessionLocal() as session:
            res = await session.execute(text("SELECT 1"))
            assert res.scalar() == 1
    finally:
        await engine.dispose()
