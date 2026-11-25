from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import get_engine

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness: the process is up."""
    return {"status": "ok"}


@router.get("/readyz", response_model=None)
async def readyz() -> dict[str, str] | JSONResponse:
    """Readiness: the process can reach its database."""
    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError):
        return JSONResponse({"status": "unavailable", "database": "unreachable"}, status_code=503)
    return {"status": "ok", "database": "ok"}
