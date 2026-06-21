from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.routers import auth, database, query, admin
from app.services.kafka_service import kafka_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    # App Startup
    await kafka_service.start()
    yield
    # App Shutdown
    await kafka_service.stop()

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="AI-Powered Natural Language Database Query Platform",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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
