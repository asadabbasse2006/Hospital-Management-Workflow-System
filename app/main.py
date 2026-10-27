from app.modules.patients.router import router as patients_router
from app.modules.laboratory.router import router as laboratory_router
from app.modules.users.router import router as users_router

from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.rate_limit import limiter
from app.modules.auth.router import router as auth_router

from app.db.session import engine

app = FastAPI(
    title="Hospital Management & Laboratory Workflow System",
    version="0.1.0",
)

app.include_router(patients_router, prefix="/api/v1")
app.include_router(laboratory_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")

app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,
)

app.include_router(auth_router, prefix="/api/v1")


@app.get("/health/live", tags=["System"])
def liveness():
    return {"status": "alive"}


@app.get("/health/ready", tags=["System"])
def readiness():
    try:
        with engine.connect() as connection:
            database_name = connection.execute(
                text("SELECT current_database()")
            ).scalar_one()

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed",
        ) from None

    return {
        "status": "ready",
        "database": database_name,
    }