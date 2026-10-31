import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import engine, Base, SessionLocal
from app.api.routes import (
    facilities, products, inventory, forecasts, risks,
    proposals, approvals, transfers, qr, agent, dashboard, audit, demo
)
from app.services.seed_service import seed_database
from app.models.organization import Facility

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("stockout_shield")


# Ensure tables are created
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Stockout Shield API",
    description="Multi-facility medicine inventory intelligence, redistribution and QR traceability platform.",
    version="1.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if settings.CORS_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routes
app.include_router(dashboard.router, prefix="/api")
app.include_router(facilities.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(inventory.router, prefix="/api")
app.include_router(forecasts.router, prefix="/api")
app.include_router(risks.router, prefix="/api")
app.include_router(proposals.router, prefix="/api")
app.include_router(approvals.router, prefix="/api")
app.include_router(transfers.router, prefix="/api")
app.include_router(qr.router, prefix="/api")
app.include_router(agent.router, prefix="/api")
app.include_router(audit.router, prefix="/api")
app.include_router(demo.router, prefix="/api")


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Stockout Shield API",
        "version": "1.0.0",
        "database": "CONNECTED",
        "simulation_mode": True
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
