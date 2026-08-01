import pytest
import uuid
import httpx
from sqlalchemy import text
from app.config import settings, Settings
from app.database import engine, SessionLocal
from app.main import app

def test_database_url_sanitization():
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
async def test_required_tables_exist():
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
            tables = [row[0] for row in res.fetchall()]
            assert "users" in tables
            assert "database_connections" in tables
            assert "query_history" in tables
            assert "audit_logs" in tables
    finally:
        await engine.dispose()

@pytest.mark.asyncio
async def test_auth_register_and_login_flow():
    await engine.dispose()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        unique_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        password = "SecurePassword123!"

        # 1. Register user
        reg_response = await ac.post(
            "/auth/register",
            json={"email": unique_email, "password": password, "role": "viewer"}
        )
        assert reg_response.status_code == 201, f"Registration failed: {reg_response.text}"
        reg_data = reg_response.json()
        assert reg_data["email"] == unique_email
        assert "id" in reg_data

        # 2. Login user
        login_response = await ac.post(
            "/auth/login",
            json={"email": unique_email, "password": password}
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        login_data = login_response.json()
        assert "access_token" in login_data
        assert "refresh_token" in login_data
        assert login_data["token_type"] == "bearer"
    await engine.dispose()
