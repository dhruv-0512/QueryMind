from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Database Configurations
    DATABASE_URL: str

    # Redis Configuration
    REDIS_URL: str

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str

    # ChromaDB Configuration
    CHROMADB_HOST: str
    CHROMADB_PORT: int

    # LLM Configuration
    GEMINI_API_KEY: str

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
