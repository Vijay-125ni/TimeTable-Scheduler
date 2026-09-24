import logging
import time
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .api.router import api_router
from .core.config import settings
from .core.logging_config import configure_logging
from .database.database import close_mongo_connection, get_client, init_indexes

# Initialize Logging
configure_logging()

logger = logging.getLogger(__name__)


def _mask_mongo_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        if "@" not in parts.netloc:
            return url
        host = parts.netloc.rsplit("@", 1)[1]
        return urlunsplit(
            (parts.scheme, f"***:***@{host}", parts.path, parts.query, parts.fragment)
        )
    except Exception:
        return "<configured MongoDB URL>"


from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")
    try:
        client = get_client()
        client.admin.command("ping")
        logger.info(
            f"[SUCCESS] Connected to MongoDB at {_mask_mongo_url(settings.active_mongodb_url)} | DB: {settings.DB_NAME}"
        )
        init_indexes(client[settings.DB_NAME])
    except Exception as e:
        logger.error(f"[ERROR] Could not connect to MongoDB: {e}")
    yield
    logger.info("Application shutting down...")
    close_mongo_connection()


app = FastAPI(
    title="AI Timetable Scheduler",
    description="Dynamic timetable scheduling using OR-Tools",
    version="1.0.0",
    lifespan=lifespan,
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_and_logging_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    logger.info(
        f"Method: {request.method} Path: {request.url.path} Status: {response.status_code} Time: {process_time:.2f}ms"
    )

    # Security Headers (Phase 4 & 14)
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self' *"
    )
    return response


app.include_router(api_router, prefix="/api")


@app.get("/")
def root():
    logger.info("Root endpoint accessed")
    return {
        "message": "AI Timetable Scheduler API",
        "docs": "/docs",
        "version": "1.0.0",
    }


@app.get("/health")
def health():
    logger.debug("Health check probe")
    return {"status": "healthy"}
