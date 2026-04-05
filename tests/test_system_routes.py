"""
Tests for built-in system routes: /metrics, /prometheus, /logs, /dashboard.
"""
import json
import os
from unittest.mock import patch, MagicMock

import pytest

from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_metrics_returns_json(client):
    with patch("peewee.PostgresqlDatabase.connect"), \
         patch("peewee.PostgresqlDatabase.is_closed", return_value=True):
        response = client.get("/metrics")
    assert response.status_code == 200
    data = response.get_json()
    assert "cpu_percent" in data
    assert "memory" in data
    assert "requests" in data
    assert "hostname" in data


def test_metrics_memory_fields(client):
    with patch("peewee.PostgresqlDatabase.connect"), \
         patch("peewee.PostgresqlDatabase.is_closed", return_value=True):
        response = client.get("/metrics")
    mem = response.get_json()["memory"]
    assert "total_mb" in mem
    assert "used_mb" in mem
    assert "available_mb" in mem
    assert "percent" in mem


def test_prometheus_endpoint_returns_text(client):
    with patch("peewee.PostgresqlDatabase.connect"), \
         patch("peewee.PostgresqlDatabase.is_closed", return_value=True):
        response = client.get("/prometheus")
    assert response.status_code == 200
    assert b"http_requests_total" in response.data or b"# HELP" in response.data


def test_logs_returns_list_when_no_file(client):
    with patch("peewee.PostgresqlDatabase.connect"), \
         patch("peewee.PostgresqlDatabase.is_closed", return_value=True), \
         patch("builtins.open", side_effect=FileNotFoundError):
        response = client.get("/logs")
    assert response.status_code == 200
    assert response.get_json() == []


def test_logs_returns_parsed_json_lines(client, tmp_path):
    log_file = tmp_path / "app.log"
    entries = [
        {"timestamp": "2024-01-01T00:00:00", "level": "INFO", "message": "request"},
        {"timestamp": "2024-01-01T00:00:01", "level": "ERROR", "message": "error"},
    ]
    log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    import app as app_module
    original = app_module.LOG_FILE
    app_module.LOG_FILE = str(log_file)
    try:
        with patch("peewee.PostgresqlDatabase.connect"), \
             patch("peewee.PostgresqlDatabase.is_closed", return_value=True):
            response = client.get("/logs?limit=10")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 2
        assert data[0]["message"] == "request"
    finally:
        app_module.LOG_FILE = original


def test_dashboard_returns_html(client):
    with patch("peewee.PostgresqlDatabase.connect"), \
         patch("peewee.PostgresqlDatabase.is_closed", return_value=True):
        response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"<html" in response.data.lower() or b"<!doctype" in response.data.lower()


def test_alert_status_returns_status(client):
    with patch("peewee.PostgresqlDatabase.connect"), \
         patch("peewee.PostgresqlDatabase.is_closed", return_value=True):
        response = client.get("/alert-status")
    # Alert manager starts with the app; status endpoint returns 200 with state
    assert response.status_code in (200, 503)
    assert response.is_json
