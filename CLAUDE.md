# traast-api

> **SDLC Root**: Traast
> **Parent skills**: `../../.claude/skills/`

## What is traast-api

Core backend API for Traast — the coordination layer handling roles, users, outreach orchestration, billing, and workflow state management.

---

## Traast Context

This project is part of the **Traast** ecosystem — an AI-native recruiting execution and intelligence platform.

- Product overview: see `traast/CLAUDE.md` and `traast/docs/product/`
- Architecture: see `traast/docs/architecture/`
- SDLC management: see `traast/SDLC.md`

---

## Architecture Role

Per ADR-001, traast-api is the **coordination layer**:

**Owns:**
- Role management (JD lifecycle, activation)
- User and tenant management
- Outreach orchestration
- Interview coordination and workflow
- Billing and payments (Stripe)
- Analytics queries
- Job creation (writes to `tr_retrieval_jobs`, `tr_matching_jobs`)
- **All database schema migrations** (Alembic)

**Does NOT own:**
- AI or data provider calls
- Candidate data retrieval
- Scoring or ranking logic

---

## Tech Stack

- Python 3.12 / FastAPI
- SQLAlchemy + Alembic (migrations)
- Supabase PostgreSQL (shared with traast-match)
- Supabase Auth (JWT validation via JWKS)
- structlog (JSON logging)
- pydantic-settings (config validation)

---

## Key Patterns

### Auth
Local JWT validation via Supabase JWKS — no per-request Supabase calls. See `app/auth/jwt.py`.

### Schema Ownership
traast-api owns ALL `tr_*` table DDL. Migrations in `alembic/versions/`. traast-match never writes migrations.

### Health Checks
- `GET /health` — liveness (no DB)
- `GET /ready` — readiness (checks DB connection)

### Deploy
Railway start command: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000`

---

## Project Structure

```
traast-api/
├── app/
│   ├── main.py              # FastAPI app + middleware
│   ├── config/settings.py   # pydantic-settings
│   ├── auth/jwt.py          # Supabase JWT validation
│   ├── db/session.py        # SQLAlchemy engine
│   └── routers/
│       └── health.py        # /health + /ready
├── alembic/
│   ├── env.py
│   └── versions/            # Migration files
├── tests/
│   ├── unit/
│   └── integration/
├── Dockerfile
├── requirements.txt
└── .env.example
```
