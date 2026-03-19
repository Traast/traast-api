# traast-api

Core backend API for Traast — coordination, workflow, and billing.

## Quick Start

```bash
# 1. Copy env file and fill in values
cp .env.example .env

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run migrations
alembic upgrade head

# 4. Start server
uvicorn app.main:app --reload --port 8000
```

## Development

```bash
pip install -r requirements-dev.txt
ruff check .
ruff format --check .
mypy app/ --ignore-missing-imports
pytest tests/unit -x --tb=short
```

## Docker

```bash
docker build -t traast-api .
docker run -p 8000:8000 --env-file .env traast-api
```
