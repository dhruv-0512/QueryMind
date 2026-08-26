import os
from typing import Dict, Any
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from pydantic import field_validator, PrivateAttr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Database Configurations
    DATABASE_URL: str
    _db_connect_args: Dict[str, Any] = PrivateAttr(default_factory=dict)

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str) -> str:
        if isinstance(v, str):
            # Convert dialect prefix to postgresql+asyncpg
            if v.startswith("postgres://"):
                v = v.replace("postgres://", "postgresql+asyncpg://", 1)
            elif v.startswith("postgresql://") and not v.startswith("postgresql+asyncpg://"):
                v = v.replace("postgresql://", "postgresql+asyncpg://", 1)

            # Strip query parameters that asyncpg rejects (e.g. sslmode)
            parsed = urlparse(v)
            if parsed.query:
                query_params = parse_qs(parsed.query)
                query_params.pop("sslmode", None)
                query_params.pop("ssl", None)
                query_params.pop("channel_binding", None)

                new_query = urlencode(query_params, doseq=True)
                v = urlunparse((
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    parsed.params,
                    new_query,
                    parsed.fragment
                ))

        return v

    def model_post_init(self, __context):
        # Configure asyncpg SSL via connect_args for cloud databases (e.g. Neon)
        raw_env_db_url = (self.DATABASE_URL or "").lower()
        parsed = urlparse(self.DATABASE_URL)
        hostname = (parsed.hostname or "").lower()

        # If Neon PostgreSQL or external host, set ssl="require" for asyncpg
        if "neon.tech" in raw_env_db_url or "neon.tech" in hostname or (hostname and hostname not in ("localhost", "127.0.0.1", "postgres", "db")):
            self._db_connect_args = {"ssl": "require"}
        else:
            self._db_connect_args = {}

    @property
    def DB_CONNECT_ARGS(self) -> Dict[str, Any]:
        return self._db_connect_args

    # Redis Configuration
    REDIS_URL: str

    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str

    # ChromaDB Configuration
    CHROMADB_HOST: str = "localhost"
    CHROMADB_PORT: int = 8000
    CHROMADB_MODE: str = "persistent"  # "persistent" or "http"
    CHROMADB_PATH: str = os.environ.get(
        "CHROMADB_PATH",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chroma_data")
    )

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

