from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ROLE_ID = str(uuid4())
TENANT_ID = str(uuid4())
JOB_ID = str(uuid4())


def _make_payload(ready=True, role_id=ROLE_ID, tenant_id=TENANT_ID):
    return {
        "type": "UPDATE",
        "table": "role_profiles",
        "schema": "public",
        "record": {
            "id": role_id,
            "user_id": tenant_id,
            "ready": ready,
        },
        "old_record": {
            "id": role_id,
            "user_id": tenant_id,
            "ready": False,
        },
    }


def _mock_engine_with_result(row):
    """Create a mock engine that returns the given row from execute().fetchone()."""
    mock_result = MagicMock()
    mock_result.fetchone.return_value = row

    mock_conn = MagicMock()
    mock_conn.execute.return_value = mock_result
    mock_conn.__enter__ = lambda self: self
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    return mock_engine


@patch("app.routers.webhooks.get_engine")
@patch("app.routers.webhooks.settings")
def test_role_activated_creates_job(mock_settings, mock_get_engine):
    mock_settings.supabase_webhook_secret = ""
    mock_get_engine.return_value = _mock_engine_with_result((JOB_ID, "pending"))

    response = client.post("/webhooks/role-activated", json=_make_payload())

    assert response.status_code == 201
    data = response.json()
    assert data["job_id"] == JOB_ID
    assert data["role_id"] == ROLE_ID
    assert data["status"] == "pending"


@patch("app.routers.webhooks.get_engine")
@patch("app.routers.webhooks.settings")
def test_duplicate_activation_returns_409(mock_settings, mock_get_engine):
    mock_settings.supabase_webhook_secret = ""
    # ON CONFLICT DO NOTHING returns no row
    mock_get_engine.return_value = _mock_engine_with_result(None)

    response = client.post("/webhooks/role-activated", json=_make_payload())

    assert response.status_code == 409
    assert "already active" in response.json()["detail"]


@patch("app.routers.webhooks.settings")
def test_deactivation_ignored(mock_settings):
    mock_settings.supabase_webhook_secret = ""

    response = client.post("/webhooks/role-activated", json=_make_payload(ready=False))

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_missing_role_id_returns_422():
    payload = {
        "type": "UPDATE",
        "table": "role_profiles",
        "schema": "public",
        "record": {"ready": True},
    }

    with patch("app.routers.webhooks.settings") as mock_settings:
        mock_settings.supabase_webhook_secret = ""
        response = client.post("/webhooks/role-activated", json=payload)

    assert response.status_code == 422


@patch("app.routers.webhooks.settings")
def test_webhook_secret_rejected(mock_settings):
    mock_settings.supabase_webhook_secret = "correct-secret"

    response = client.post(
        "/webhooks/role-activated",
        json=_make_payload(),
        headers={"x-webhook-secret": "wrong-secret"},
    )

    assert response.status_code == 401


@patch("app.routers.webhooks.get_engine")
@patch("app.routers.webhooks.settings")
def test_webhook_secret_accepted(mock_settings, mock_get_engine):
    mock_settings.supabase_webhook_secret = "correct-secret"
    mock_get_engine.return_value = _mock_engine_with_result((JOB_ID, "pending"))

    response = client.post(
        "/webhooks/role-activated",
        json=_make_payload(),
        headers={"x-webhook-secret": "correct-secret"},
    )

    assert response.status_code == 201
