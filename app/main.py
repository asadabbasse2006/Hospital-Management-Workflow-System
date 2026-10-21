from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine

app = FastAPI(
    title="Hospital Management & Laboratory Workflow System",
    version="0.1.0",
)


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