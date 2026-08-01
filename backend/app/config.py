from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Database Configurations
    DATABASE_URL: str

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str) -> str:
        if isinstance(v, str):
            if v.startswith("postgres://"):
                v = v.replace("postgres://", "postgresql+asyncpg://", 1)
            elif v.startswith("postgresql://") and not v.startswith("postgresql+asyncpg://"):
                v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # Redis Configuration
    REDIS_URL: str

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str

    # ChromaDB Configuration
    CHROMADB_HOST: str
    CHROMADB_PORT: int

    # LLM Configuration
    GEMINI_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    LLM_PROVIDER: str = "deepseek"

    # Embeddings: local (no quota), gemini (API), auto (gemini with local fallback)
    EMBEDDING_PROVIDER: str = "local"

    # Security Configurations
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Application Settings
    BACKEND_PORT: int = 8000
    FRONTEND_PORT: int = 3000
    LOG_LEVEL: str = "INFO"

    # Pydantic Configuration
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

