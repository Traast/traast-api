import hmac
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
import structlog

from app.config.settings import settings
from app.db.session import get_engine

logger = structlog.get_logger()
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class RoleActivatedPayload(BaseModel):
    """Supabase DB Webhook payload for role_profiles.ready flip.

    Supabase sends: { type, table, schema, record, old_record }
    We extract role_id and tenant_id from the record.
    """
    type: str  # "UPDATE"
    table: str  # "role_profiles"
    db_schema: str = Field(alias="schema")  # "public"
    record: dict
    old_record: dict | None = None


class RetrievalJobResponse(BaseModel):
    job_id: str
    role_id: str
    status: str


@router.post("/role-activated", status_code=status.HTTP_201_CREATED)
def role_activated(request: Request, payload: RoleActivatedPayload):
    """Handle Supabase DB Webhook when a role is activated (ready = true).

    Idempotent: uses the partial unique index on tr_retrieval_jobs(role_id)
    WHERE status IN ('pending', 'running') to prevent duplicate active jobs.
    A second webhook fire for the same role is safely ignored.
    """
    # Validate webhook secret if configured
    webhook_secret = settings.supabase_webhook_secret
    if webhook_secret:
        provided_secret = request.headers.get("x-webhook-secret", "")
        if not hmac.compare_digest(provided_secret, webhook_secret):
            logger.warning("webhook_auth_failed", path="/webhooks/role-activated")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook secret",
            )

    record = payload.record
    role_id = record.get("id")
    tenant_id = record.get("user_id")
    ready = record.get("ready")

    if not role_id or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing role_id (record.id) or tenant_id (record.user_id)",
        )

    try:
        UUID(str(role_id))
        UUID(str(tenant_id))
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="role_id and tenant_id must be valid UUIDs",
        )

    # Only process activations (ready = true), ignore deactivations
    if not ready:
        logger.info("role_deactivated_ignored", role_id=role_id)
        return JSONResponse(
            status_code=200,
            content={"status": "ignored", "reason": "role not activated (ready=false)"},
        )

    logger.info("role_activation_received", role_id=role_id, tenant_id=tenant_id)

    engine = get_engine()
    with engine.connect() as conn:
        # Idempotent insert — ON CONFLICT on the partial unique index
        # (role_id WHERE status IN ('pending', 'running')) means:
        # - If no active job exists: insert succeeds
        # - If active job already exists: DO NOTHING (no error, no duplicate)
        result = conn.execute(
            text("""
                INSERT INTO tr_retrieval_jobs (role_id, tenant_id, status, created_at)
                VALUES (:role_id, :tenant_id, 'pending', NOW())
                ON CONFLICT (role_id) WHERE status IN ('pending', 'running')
                DO NOTHING
                RETURNING id, status
            """),
            {"role_id": role_id, "tenant_id": tenant_id},
        )
        row = result.fetchone()
        conn.commit()

    if row is None:
        # ON CONFLICT fired — a job is already pending or running
        logger.info("duplicate_activation_rejected", role_id=role_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A retrieval job is already active for role {role_id}",
        )

    job_id = str(row[0])
    logger.info("retrieval_job_created", job_id=job_id, role_id=role_id, tenant_id=tenant_id)

    return RetrievalJobResponse(job_id=job_id, role_id=str(role_id), status="pending")
