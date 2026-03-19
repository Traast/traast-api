"""Create initial tr_* tables per ADR-003

Revision ID: 001
Revises:
Create Date: 2026-03-19

Tables:
- tr_coresignal_profiles: Raw Coresignal API responses
- tr_candidates: Global candidate records (deduped by coresignal_id)
- tr_role_candidates: Links candidates to roles with pipeline stage
- tr_retrieval_jobs: Async retrieval job queue
- tr_ai_usage: Centralized AI/data operation cost and quality logging

Indexes:
- GIN indexes on JSONB columns for matching engine queries
- Partial indexes on tr_retrieval_jobs for worker poll and reaper queries
- Analytics indexes on tr_ai_usage
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─────────────────────────────────────────────
    # TALENT DATA (Capability #2)
    # ─────────────────────────────────────────────

    op.create_table(
        "tr_coresignal_profiles",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("coresignal_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column("linkedin_url", sa.Text),
        sa.Column("full_name", sa.Text),
        sa.Column("raw_data", JSONB),
        sa.Column("fetched_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
    )

    op.create_table(
        "tr_candidates",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("coresignal_id", sa.BigInteger, unique=True),
        sa.Column(
            "profile_id", UUID(as_uuid=True), sa.ForeignKey("tr_coresignal_profiles.id")
        ),
        # identity
        sa.Column("full_name", sa.Text),
        sa.Column("first_name", sa.Text),
        sa.Column("last_name", sa.Text),
        sa.Column("headline", sa.Text),
        sa.Column("summary", sa.Text),
        sa.Column("linkedin_url", sa.Text),
        sa.Column("avatar_url", sa.Text),
        # location
        sa.Column("location_full", sa.Text),
        sa.Column("location_country", sa.Text),
        sa.Column("location_country_iso2", sa.String(2)),
        sa.Column("location_city", sa.Text),
        sa.Column("location_state", sa.Text),
        # professional status
        sa.Column("is_working", sa.Boolean),
        sa.Column("is_decision_maker", sa.Boolean),
        sa.Column("total_experience_months", sa.Integer),
        sa.Column("active_company_name", sa.Text),
        sa.Column("active_position_title", sa.Text),
        sa.Column("active_management_level", sa.Text),
        # structured arrays
        sa.Column("experience", JSONB),
        sa.Column("education", JSONB),
        sa.Column("certifications", JSONB),
        sa.Column("inferred_skills", sa.ARRAY(sa.Text)),
        sa.Column("languages", JSONB),
        # NOTE: professional_emails intentionally excluded
        #       Personal email enrichment happens at outreach time only (Capability #4)
        # compensation
        sa.Column("projected_salary_median", sa.Numeric),
        sa.Column("projected_salary_currency", sa.Text),
        # metadata
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
    )

    op.create_table(
        "tr_role_candidates",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("role_id", UUID(as_uuid=True), nullable=False),
        # NOTE: role_id references role_profiles.id (skipy-mvp) for now.
        #       Will reference tr_roles.id when traast-api owns roles.
        #       See ADR-003 for FK migration plan.
        sa.Column(
            "candidate_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tr_candidates.id"),
            nullable=False,
        ),
        sa.Column("stage", sa.Text, server_default="prospect"),
        # stage values: prospect | contacted | screening | interview | hired | rejected
        sa.Column(
            "added_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.UniqueConstraint(
            "role_id", "candidate_id", name="uq_tr_role_candidates_role_candidate"
        ),
    )

    # ─────────────────────────────────────────────
    # JOB QUEUE (Async workers)
    # ─────────────────────────────────────────────

    op.create_table(
        "tr_retrieval_jobs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("role_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        # status values: pending | running | completed | failed
        sa.Column("query_params", JSONB),
        sa.Column("result_count", sa.Integer),
        sa.Column("new_count", sa.Integer),
        sa.Column("existing_count", sa.Integer),
        sa.Column("error", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        # NOTE: no table-wide UNIQUE(role_id) — multiple jobs per role allowed
        #       (completed, failed = historical; re-fetch creates new jobs)
        #       Concurrency guard is a partial unique index (see below)
    )

    # ─────────────────────────────────────────────
    # AI EVALUATION FRAMEWORK (Cross-cutting)
    # ─────────────────────────────────────────────

    op.create_table(
        "tr_ai_usage",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("operation_type", sa.Text, nullable=False),
        # operation_type values:
        #   Coresignal: 'coresignal_query' | 'coresignal_collect'
        #   Claude:     'claude_matching'  | 'claude_screening' | 'claude_jd_analysis'
        sa.Column("provider", sa.Text, nullable=False),
        # provider values: 'coresignal' | 'anthropic'
        # entity context
        sa.Column("role_id", UUID(as_uuid=True)),
        sa.Column("candidate_id", UUID(as_uuid=True)),
        sa.Column("job_id", UUID(as_uuid=True)),
        # cost tracking
        sa.Column("units_consumed", sa.Integer),
        sa.Column("cost_usd", sa.Numeric(10, 6)),
        sa.Column("unit_cost_usd", sa.Numeric(10, 6)),
        # quality (for LLM evaluations)
        sa.Column("quality_score", sa.Numeric(3, 2)),
        # performance
        sa.Column("duration_ms", sa.Integer),
        # details
        sa.Column("metadata", JSONB),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
    )

    # ─────────────────────────────────────────────
    # INDEXES (per ADR-003)
    # ─────────────────────────────────────────────

    # tr_candidates: matching engine queries inside JSONB columns
    op.execute(
        "CREATE INDEX idx_tr_candidates_experience ON tr_candidates USING GIN (experience)"
    )
    op.execute(
        "CREATE INDEX idx_tr_candidates_education ON tr_candidates USING GIN (education)"
    )
    op.execute(
        "CREATE INDEX idx_tr_candidates_skills ON tr_candidates USING GIN (inferred_skills)"
    )

    # tr_retrieval_jobs: one active job per role (partial unique index)
    # Allows unlimited historical rows (completed, failed) while preventing
    # concurrent active jobs for the same role.
    op.execute("""
        CREATE UNIQUE INDEX idx_tr_retrieval_jobs_one_active_per_role
            ON tr_retrieval_jobs (role_id)
            WHERE status IN ('pending', 'running')
    """)

    # tr_retrieval_jobs: worker poll queries filter on status
    # Partial index covers the only rows workers care about
    op.execute("""
        CREATE INDEX idx_tr_retrieval_jobs_pending
            ON tr_retrieval_jobs (created_at ASC)
            WHERE status = 'pending'
    """)

    # tr_retrieval_jobs: reaper query (status=running AND started_at < threshold)
    op.execute("""
        CREATE INDEX idx_tr_retrieval_jobs_running
            ON tr_retrieval_jobs (started_at)
            WHERE status = 'running'
    """)

    # tr_ai_usage: analytics queries by tenant, role, and time
    op.execute(
        "CREATE INDEX idx_tr_ai_usage_tenant_role ON tr_ai_usage (tenant_id, role_id)"
    )
    op.execute("CREATE INDEX idx_tr_ai_usage_job ON tr_ai_usage (job_id)")
    op.execute("CREATE INDEX idx_tr_ai_usage_created ON tr_ai_usage (created_at DESC)")


def downgrade() -> None:
    # Drop indexes first (some are implicit with tables, but explicit ones need dropping)
    op.execute("DROP INDEX IF EXISTS idx_tr_ai_usage_created")
    op.execute("DROP INDEX IF EXISTS idx_tr_ai_usage_job")
    op.execute("DROP INDEX IF EXISTS idx_tr_ai_usage_tenant_role")
    op.execute("DROP INDEX IF EXISTS idx_tr_retrieval_jobs_running")
    op.execute("DROP INDEX IF EXISTS idx_tr_retrieval_jobs_pending")
    op.execute("DROP INDEX IF EXISTS idx_tr_retrieval_jobs_one_active_per_role")
    op.execute("DROP INDEX IF EXISTS idx_tr_candidates_skills")
    op.execute("DROP INDEX IF EXISTS idx_tr_candidates_education")
    op.execute("DROP INDEX IF EXISTS idx_tr_candidates_experience")

    # Drop tables in reverse dependency order
    op.drop_table("tr_ai_usage")
    op.drop_table("tr_retrieval_jobs")
    op.drop_table("tr_role_candidates")
    op.drop_table("tr_candidates")
    op.drop_table("tr_coresignal_profiles")
