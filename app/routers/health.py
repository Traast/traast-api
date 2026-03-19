from fastapi import APIRouter
from fastapi.responses import JSONResponse
import structlog
from sqlalchemy import text
from app.db.session import get_engine

logger = structlog.get_logger()
router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/ready")
async def ready():
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        logger.error("Readiness check failed", error=str(e))
        return JSONResponse(
            status_code=503, content={"status": "unavailable", "error": str(e)}
        )
