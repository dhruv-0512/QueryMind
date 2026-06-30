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

# Configure CORS — allow override via CORS_ORIGINS env var (comma-separated)
_default_origins = ["http://localhost:3000", "http://localhost:5173"]
_cors_origins = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else _default_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
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
