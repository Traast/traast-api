from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt import get_current_user
from app.main import app

ROLE_ID = str(uuid4())
TENANT_ID = str(uuid4())
JOB_ID = str(uuid4())
CANDIDATE_ID = str(uuid4())

AUTH_HEADER = {"Authorization": "Bearer fake-token"}

FAKE_USER = {"sub": TENANT_ID, "email": "test@example.com"}


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    yield
    app.dependency_overrides.clear()


client = TestClient(app)


def _mock_engine_with_rows(rows, fetchone=None):
    mock_result = MagicMock()
    mock_result.fetchall.return_value = rows if rows is not None else []
    mock_result.fetchone.return_value = fetchone

    mock_conn = MagicMock()
    mock_conn.execute.return_value = mock_result
    mock_conn.__enter__ = lambda self: self
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    return mock_engine


def _mock_engine_multi_queries(results):
    mock_conn = MagicMock()
    mock_results = []
    for r in results:
        mr = MagicMock()
        mr.fetchone.return_value = r.get("fetchone")
        mr.fetchall.return_value = r.get("fetchall", [])
        mock_results.append(mr)
    mock_conn.execute.side_effect = mock_results
    mock_conn.__enter__ = lambda self: self
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    return mock_engine


# ── GET /roles/{role_id}/retrieval-status ────────────────────────


@patch("app.routers.roles.get_engine")
def test_retrieval_status_completed(mock_get_engine):
    now = datetime.now(timezone.utc)
    mock_get_engine.return_value = _mock_engine_with_rows(
        rows=None,
        fetchone=("completed", 127, 115, 12, None, now, now, now),
    )

    response = client.get(f"/roles/{ROLE_ID}/retrieval-status", headers=AUTH_HEADER)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["result_count"] == 127
    assert data["new_count"] == 115
    assert data["existing_count"] == 12
    assert data["error"] is None


@patch("app.routers.roles.get_engine")
def test_retrieval_status_running(mock_get_engine):
    now = datetime.now(timezone.utc)
    mock_get_engine.return_value = _mock_engine_with_rows(
        rows=None,
        fetchone=("running", None, None, None, None, now, now, None),
    )

    response = client.get(f"/roles/{ROLE_ID}/retrieval-status", headers=AUTH_HEADER)

    assert response.status_code == 200
    assert response.json()["status"] == "running"


@patch("app.routers.roles.get_engine")
def test_retrieval_status_failed(mock_get_engine):
    now = datetime.now(timezone.utc)
    mock_get_engine.return_value = _mock_engine_with_rows(
        rows=None,
        fetchone=("failed", 0, 0, 0, "Provider timeout", now, now, now),
    )

    response = client.get(f"/roles/{ROLE_ID}/retrieval-status", headers=AUTH_HEADER)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["error"] == "Provider timeout"


@patch("app.routers.roles.get_engine")
def test_retrieval_status_not_found(mock_get_engine):
    mock_get_engine.return_value = _mock_engine_with_rows(rows=None, fetchone=None)

    response = client.get(f"/roles/{ROLE_ID}/retrieval-status", headers=AUTH_HEADER)

    assert response.status_code == 404


def test_retrieval_status_invalid_uuid():
    response = client.get("/roles/not-a-uuid/retrieval-status", headers=AUTH_HEADER)
    assert response.status_code == 422


# ── GET /roles/{role_id}/candidates ──────────────────────────────


@patch("app.routers.roles.get_engine")
def test_candidates_returns_pool(mock_get_engine):
    mock_get_engine.return_value = _mock_engine_multi_queries([
        {"fetchone": (3,)},
        {
            "fetchall": [
                (
                    CANDIDATE_ID, "Jane Doe", "Senior Engineer", "Acme Corp",
                    "San Francisco, CA", 60, ["Python", "FastAPI", "PostgreSQL", "React"],
                    "prospect",
                ),
                (
                    str(uuid4()), "John Smith", "Tech Lead", "BigCo",
                    "New York, NY", 120, ["Java", "Spring"], "prospect",
                ),
                (
                    str(uuid4()), None, None, None, None, None, None, "prospect",
                ),
            ]
        },
    ])

    response = client.get(f"/roles/{ROLE_ID}/candidates", headers=AUTH_HEADER)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["candidates"]) == 3

    jane = data["candidates"][0]
    assert jane["full_name"] == "Jane Doe"
    assert jane["total_experience_years"] == 5.0
    assert jane["top_skills"] == ["Python", "FastAPI", "PostgreSQL"]
    assert len(jane["top_skills"]) == 3


@patch("app.routers.roles.get_engine")
def test_candidates_empty_pool(mock_get_engine):
    mock_get_engine.return_value = _mock_engine_multi_queries([
        {"fetchone": (0,)},
        {"fetchall": []},
    ])

    response = client.get(f"/roles/{ROLE_ID}/candidates", headers=AUTH_HEADER)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["candidates"] == []


@patch("app.routers.roles.get_engine")
def test_candidates_pagination(mock_get_engine):
    mock_get_engine.return_value = _mock_engine_multi_queries([
        {"fetchone": (50,)},
        {"fetchall": []},
    ])

    response = client.get(
        f"/roles/{ROLE_ID}/candidates?limit=10&offset=20", headers=AUTH_HEADER
    )

    assert response.status_code == 200
    assert response.json()["total"] == 50


# ── POST /roles/{role_id}/retrieval/retry ────────────────────────


@patch("app.routers.roles.get_engine")
def test_retry_creates_job(mock_get_engine):
    mock_get_engine.return_value = _mock_engine_multi_queries([
        {"fetchone": None},
        {"fetchone": (JOB_ID, "pending")},
    ])

    response = client.post(f"/roles/{ROLE_ID}/retrieval/retry", headers=AUTH_HEADER)

    assert response.status_code == 201
    data = response.json()
    assert data["job_id"] == JOB_ID
    assert data["status"] == "pending"


@patch("app.routers.roles.get_engine")
def test_retry_rate_limited(mock_get_engine):
    now = datetime.now(timezone.utc)
    mock_get_engine.return_value = _mock_engine_multi_queries([
        {"fetchone": (str(uuid4()), now)},
    ])

    response = client.post(f"/roles/{ROLE_ID}/retrieval/retry", headers=AUTH_HEADER)

    assert response.status_code == 429
    assert "rate-limited" in response.json()["detail"]


@patch("app.routers.roles.get_engine")
def test_retry_conflict_active_job(mock_get_engine):
    mock_get_engine.return_value = _mock_engine_multi_queries([
        {"fetchone": None},
        {"fetchone": None},
    ])

    response = client.post(f"/roles/{ROLE_ID}/retrieval/retry", headers=AUTH_HEADER)

    assert response.status_code == 409
    assert "already active" in response.json()["detail"]
