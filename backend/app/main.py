import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, database, query, admin
from app.services.kafka_service import kafka_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # App Startup
    await kafka_service.start()

    # Preload the embedding model so the first query doesn't time out
    from app.utils.embeddings import _provider, _get_local_model

    if _provider() in ("local", "auto"):
        import asyncio
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _get_local_model)
        logger.info("Embedding model preloaded successfully")

    yield
    # App Shutdown
    await kafka_service.stop()

app = FastAPI(
    title="AI-Powered Natural Language Database Query Platform",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
# Always allow production Vercel frontend, localhost dev environments, and Vercel previews
_default_origins = [
    "https://query-mind-brown.vercel.app",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
]

_env_origins_raw = os.getenv("CORS_ORIGINS", "")
_parsed_env_origins = [origin.strip() for origin in _env_origins_raw.split(",") if origin.strip()]

_allowed_origins = set(_default_origins)
for _origin in _parsed_env_origins:
    if _origin == "*":
        _allowed_origins.add("*")
    elif "*" not in _origin:
        _allowed_origins.add(_origin.rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_allowed_origins),
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth.router)
app.include_router(database.router)
app.include_router(query.router)
app.include_router(admin.router)

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
