import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine, Base, SessionLocal, is_live_yugabyte
from app.api.routes import (
    facilities, products, inventory, forecasts, risks,
    proposals, approvals, transfers, qr, agent, dashboard, audit, demo, imports
)
from app.integrations.gemini import gemini_adapter
from app.integrations.meko import meko_adapter

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("mediflow")

# Ensure tables are created -- gracefully handle unreachable DBs at startup
_db_init_error = None
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified/created successfully.")
except Exception as _db_exc:
    _db_init_error = str(_db_exc)
    logger.warning(
        "Could not auto-create DB tables at startup: %s. "
        "App will start but DB operations may fail.",
        _db_exc
    )

app = FastAPI(
    title="MediFlow API",
    description="Multi-facility medicine inventory intelligence, redistribution and QR traceability platform.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if settings.CORS_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Consistent Error Handling Conventions
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "error": {
                "code": exc.status_code,
                "message": exc.detail,
                "type": "http_exception"
            },
            "detail": exc.detail
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    message = "Request validation failed"
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "error",
            "error": {
                "code": 422,
                "message": message,
                "details": errors,
                "type": "validation_error"
            },
            "detail": errors
        }
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled server error on {request.url.path}: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "error": {
                "code": 500,
                "message": "Internal server error occurred",
                "type": "internal_server_error"
            },
            "detail": "An internal server error occurred. Please consult backend logs."
        }
    )


# Health Check Handler
def compute_health_status():
    db_status = "UNKNOWN"
    db_dialect = "postgresql/yugabyte" if is_live_yugabyte else "sqlite_fallback"
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        db_status = "CONNECTED"
    except Exception as e:
        logger.error(f"Health check database failure: {e}")
        db_status = f"ERROR: {str(e)}"

    return {
        "status": "healthy" if db_status == "CONNECTED" else "degraded",
        "service": settings.APP_NAME,
        "version": "1.0.0",
        "environment": settings.APP_ENV,
        "database": {
            "status": db_status,
            "engine": db_dialect,
            "is_fallback": not is_live_yugabyte
        },
        "integrations": {
            "gemini": gemini_adapter.get_status(),
            "meko": meko_adapter.get_status()
        },
        "simulation_mode": True,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/health", tags=["Health"])
@app.get("/api/health", tags=["Health"])
@app.get("/api/v1/health", tags=["Health"])
def health_check():
    return compute_health_status()


# Mount versioned API routes (/api/v1) as canonical endpoints
v1_routers = [
    dashboard.router,
    facilities.router,
    products.router,
    inventory.router,
    forecasts.router,
    risks.router,
    proposals.router,
    approvals.router,
    transfers.router,
    qr.router,
    agent.router,
    audit.router,
    demo.router,
    imports.router
]

for router in v1_routers:
    app.include_router(router, prefix="/api/v1")
    # Also mount under /api for backward compatibility
    app.include_router(router, prefix="/api")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
