import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import engine
from app.models.models import Base
from app.api import auth, donations, requests, matching, deliveries, analytics, websockets
from app.api import admin, volunteers
from app.core.rate_limit import rate_limit_middleware
from app.workers.background import start_background_workers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables (use Alembic in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Create tables automatically during startup (useful for local dev/testing)
    # In production environments, it's recommended to use 'alembic upgrade head'
    if os.getenv("CREATE_TABLES", "true").lower() == "true":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Create upload directory
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    # Start background workers
    await start_background_workers()

    logger.info("FoodBridge backend started ✅")
    yield

    await engine.dispose()
    logger.info("FoodBridge backend stopped")


app = FastAPI(
    title="FoodBridge API",
    description="Real-time intelligent food distribution platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5500", "http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limit_middleware)

# Static file serving for uploaded images
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# Routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(donations.router, prefix="/api/v1")
app.include_router(requests.router, prefix="/api/v1")
app.include_router(matching.router, prefix="/api/v1")
app.include_router(deliveries.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(volunteers.router, prefix="/api/v1")
app.include_router(websockets.router)  # WebSocket routes at root level


@app.get("/health")
async def health():
    return {"status": "ok", "service": "FoodBridge API"}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
