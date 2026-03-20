from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
import structlog

from app.auth.jwt import get_current_user
from app.db.session import get_engine

logger = structlog.get_logger()
router = APIRouter(prefix="/roles", tags=["roles"])


# ── Response models ──────────────────────────────────────────────


class RetrievalStatusResponse(BaseModel):
    role_id: str
    status: str  # pending | running | completed | failed
    result_count: int | None = None
    new_count: int | None = None
    existing_count: int | None = None
    error: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class CandidateSummary(BaseModel):
    id: str
    full_name: str | None = None
    active_position_title: str | None = None
    active_company_name: str | None = None
    location_full: str | None = None
    total_experience_years: float | None = None
    top_skills: list[str] = []
    stage: str = "prospect"


class CandidatePoolResponse(BaseModel):
    role_id: str
    total: int
    candidates: list[CandidateSummary]


class RetryResponse(BaseModel):
    job_id: str
    role_id: str
    status: str


# ── Endpoints ────────────────────────────────────────────────────


@router.get("/{role_id}/retrieval-status")
def get_retrieval_status(
    role_id: UUID,
    user: dict = Depends(get_current_user),
) -> RetrievalStatusResponse:
    """Get the latest retrieval job status for a role."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT status, result_count, new_count, existing_count,
                       error, created_at, started_at, completed_at
                FROM tr_retrieval_jobs
                WHERE role_id = :role_id
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"role_id": str(role_id)},
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No retrieval job found for role {role_id}",
        )

    def _iso(dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None

    return RetrievalStatusResponse(
        role_id=str(role_id),
        status=row[0],
        result_count=row[1],
        new_count=row[2],
        existing_count=row[3],
        error=row[4],
        created_at=_iso(row[5]),
        started_at=_iso(row[6]),
        completed_at=_iso(row[7]),
    )


@router.get("/{role_id}/candidates")
def get_candidates(
    role_id: UUID,
    user: dict = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> CandidatePoolResponse:
    """Get the candidate pool for a role from tr_role_candidates + tr_candidates."""
    engine = get_engine()
    with engine.connect() as conn:
        count_row = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM tr_role_candidates
                WHERE role_id = :role_id
            """),
            {"role_id": str(role_id)},
        ).fetchone()
        total = count_row[0] if count_row else 0

        rows = conn.execute(
            text("""
                SELECT c.id, c.full_name, c.active_position_title,
                       c.active_company_name, c.location_full,
                       c.total_experience_months, c.inferred_skills,
                       rc.stage
                FROM tr_role_candidates rc
                JOIN tr_candidates c ON c.id = rc.candidate_id
                WHERE rc.role_id = :role_id
                ORDER BY rc.added_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {"role_id": str(role_id), "limit": limit, "offset": offset},
        ).fetchall()

    candidates = []
    for row in rows:
        experience_months = row[5]
        experience_years = (
            round(experience_months / 12, 1) if experience_months else None
        )
        skills = row[6] or []
        candidates.append(
            CandidateSummary(
                id=str(row[0]),
                full_name=row[1],
                active_position_title=row[2],
                active_company_name=row[3],
                location_full=row[4],
                total_experience_years=experience_years,
                top_skills=skills[:3],
                stage=row[7] or "prospect",
            )
        )

    return CandidatePoolResponse(
        role_id=str(role_id),
        total=total,
        candidates=candidates,
    )


@router.post(
    "/{role_id}/retrieval/retry",
    status_code=status.HTTP_201_CREATED,
)
def retry_retrieval(
    role_id: UUID,
    user: dict = Depends(get_current_user),
) -> RetryResponse:
    """Create a new retrieval job for a role. Rate-limited to 1 per 24 hours."""
    tenant_id = user.get("sub")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing sub claim",
        )

    engine = get_engine()
    with engine.connect() as conn:
        # Check 24h rate limit — any job created in the last 24 hours blocks retry
        recent = conn.execute(
            text("""
                SELECT id, created_at
                FROM tr_retrieval_jobs
                WHERE role_id = :role_id
                  AND created_at > NOW() - INTERVAL '24 hours'
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"role_id": str(role_id)},
        ).fetchone()

        if recent:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Re-fetch is rate-limited to once per 24 hours for this role",
            )

        # Insert new pending job (same idempotent insert as webhook)
        result = conn.execute(
            text("""
                INSERT INTO tr_retrieval_jobs (role_id, tenant_id, status, created_at)
                VALUES (:role_id, :tenant_id, 'pending', NOW())
                ON CONFLICT (role_id) WHERE status IN ('pending', 'running')
                DO NOTHING
                RETURNING id, status
            """),
            {"role_id": str(role_id), "tenant_id": tenant_id},
        )
        row = result.fetchone()
        conn.commit()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A retrieval job is already active for role {role_id}",
        )

    job_id = str(row[0])
    logger.info("retrieval_retry_created", job_id=job_id, role_id=str(role_id))

    return RetryResponse(job_id=job_id, role_id=str(role_id), status="pending")
