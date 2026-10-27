from unittest.mock import patch
import pytest
from sqlalchemy.exc import OperationalError


def test_health_live_endpoint(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_health_ready_endpoint_healthy(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert "database" in data
    assert data["database"] is not None


def test_health_ready_endpoint_db_failure(client):
    with patch("app.main.engine.connect") as mock_connect:
        mock_connect.side_effect = OperationalError("Connection refused", {}, None)
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["detail"] == "Database connection failed"
