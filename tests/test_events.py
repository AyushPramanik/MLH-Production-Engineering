"""
Tests for POST /events and GET /events with filters.
"""
from unittest.mock import MagicMock, patch

import pytest

from app import create_app
from app.models.event import Event


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _mock_event():
    e = MagicMock()
    e.id = 1
    e.url_id = 1
    e.user_id = None
    e.event_type = "created"
    e.timestamp = "2024-01-01T00:00:00"
    e.details = None
    return e


def test_create_event_success(client):
    mock_event = _mock_event()
    with patch("peewee.PostgresqlDatabase.connect"), \
         patch("peewee.PostgresqlDatabase.is_closed", return_value=True), \
         patch("app.routes.events.Event.create", return_value=mock_event):
        response = client.post("/events", json={"url_id": 1, "event_type": "created"})
    assert response.status_code == 201
    data = response.get_json()
    assert data["event_type"] == "created"
    assert data["url_id"] == 1


def test_create_event_missing_fields(client):
    with patch("peewee.PostgresqlDatabase.connect"), \
         patch("peewee.PostgresqlDatabase.is_closed", return_value=True):
        response = client.post("/events", json={"url_id": 1})
    assert response.status_code == 400
    assert "required" in response.get_json()["error"]


def test_create_event_missing_url_id(client):
    with patch("peewee.PostgresqlDatabase.connect"), \
         patch("peewee.PostgresqlDatabase.is_closed", return_value=True):
        response = client.post("/events", json={"event_type": "created"})
    assert response.status_code == 400


def test_create_event_with_dict_details(client):
    mock_event = _mock_event()
    mock_event.details = '{"key": "value"}'
    with patch("peewee.PostgresqlDatabase.connect"), \
         patch("peewee.PostgresqlDatabase.is_closed", return_value=True), \
         patch("app.routes.events.Event.create", return_value=mock_event):
        response = client.post("/events", json={
            "url_id": 1,
            "event_type": "created",
            "details": {"key": "value"},
        })
    assert response.status_code == 201


def test_create_event_with_user_id(client):
    mock_event = _mock_event()
    mock_event.user_id = 5
    with patch("peewee.PostgresqlDatabase.connect"), \
         patch("peewee.PostgresqlDatabase.is_closed", return_value=True), \
         patch("app.routes.events.Event.create", return_value=mock_event):
        response = client.post("/events", json={
            "url_id": 1,
            "event_type": "created",
            "user_id": 5,
        })
    assert response.status_code == 201
    assert response.get_json()["user_id"] == 5


def test_list_events_with_url_id_filter(client):
    mock_event = _mock_event()
    with patch("peewee.PostgresqlDatabase.connect"), \
         patch("peewee.PostgresqlDatabase.is_closed", return_value=True), \
         patch("app.routes.events.Event.select") as mock_select:
        mock_query = MagicMock()
        mock_select.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.__iter__ = lambda self: iter([mock_event])
        response = client.get("/events?url_id=1")
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)


def test_list_events_with_event_type_filter(client):
    with patch("peewee.PostgresqlDatabase.connect"), \
         patch("peewee.PostgresqlDatabase.is_closed", return_value=True), \
         patch("app.routes.events.Event.select") as mock_select:
        mock_query = MagicMock()
        mock_select.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.__iter__ = lambda self: iter([])
        response = client.get("/events?event_type=deleted")
    assert response.status_code == 200
    assert response.get_json() == []


def test_event_dict_parses_json_details(client):
    mock_event = _mock_event()
    mock_event.details = '{"action": "test"}'
    with patch("peewee.PostgresqlDatabase.connect"), \
         patch("peewee.PostgresqlDatabase.is_closed", return_value=True), \
         patch("app.routes.events.Event.get_by_id", return_value=mock_event):
        response = client.get("/events/1")
    assert response.status_code == 200
    assert response.get_json()["details"] == {"action": "test"}
