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
from app.core.database import (
    Base,
    SessionLocal,
    dispose_engine,
    fallback_to_sqlite,
    get_engine,
    initialize_database,
    is_yugabyte_active,
    ensure_audit_correlation_schema,
)
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    try:
        startup_was_yugabyte = is_yugabyte_active()
        try:
            Base.metadata.create_all(bind=get_engine())
            ensure_audit_correlation_schema(get_engine())
            logger.info("Database schema verified/created.")
        except Exception as exc:
            fallback_switched = fallback_to_sqlite(exc)
            if not fallback_switched and not (
                startup_was_yugabyte and not is_yugabyte_active()
            ):
                raise
            Base.metadata.create_all(bind=get_engine())
            ensure_audit_correlation_schema(get_engine())
            logger.warning("Database schema initialized on SQLite fallback.")
        yield
    finally:
        dispose_engine()

app = FastAPI(
    title="MediFlow API",
    description="Multi-facility medicine inventory intelligence, redistribution and QR traceability platform.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
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
    health_check_started_on_yugabyte = is_yugabyte_active()
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        db_status = "CONNECTED"
    except Exception as e:
        logger.error("Health check database failure: %s", type(e).__name__)
        switched_to_sqlite = fallback_to_sqlite(e) or (
            health_check_started_on_yugabyte and not is_yugabyte_active()
        )
        if switched_to_sqlite:
            try:
                with SessionLocal() as db:
                    db.execute(text("SELECT 1"))
                db_status = "CONNECTED"
            except Exception as fallback_error:
                logger.exception("SQLite fallback health check failed.")
                db_status = f"ERROR: {type(fallback_error).__name__}"
        else:
            db_status = f"ERROR: {type(e).__name__}"

    using_yugabyte = is_yugabyte_active()
    configured_database = "postgresql/yugabyte" if settings.is_yugabyte else "sqlite"
    active_database = "postgresql/yugabyte" if using_yugabyte else "sqlite"
    return {
        "status": "healthy" if db_status == "CONNECTED" else "degraded",
        "service": settings.APP_NAME,
        "version": "1.0.0",
        "environment": settings.APP_ENV,
        "database": {
            "status": db_status,
            "engine": active_database,
            "configured_engine": configured_database,
            "is_fallback": settings.is_yugabyte and not using_yugabyte
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
