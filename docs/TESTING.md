# Testing Guide

## Running the Tests

```bash
# Run all tests with coverage report
uv run pytest

# Run a single test file
uv run pytest tests/test_integration.py

# Run a specific test
uv run pytest tests/test_integration.py::test_full_lifecycle

# Run with verbose output
uv run pytest -v

# Run without coverage (faster feedback loop)
uv run pytest --no-cov
```

Tests must maintain **50% coverage** or the suite fails (configured in `pyproject.toml`). Current coverage is well above this threshold.

---

## Test Structure

```
tests/
├── test_health.py       # System endpoint smoke tests
├── test_graceful.py     # Error handling and all CRUD routes (mocked DB)
├── test_integration.py  # Full pipeline tests (real SQLite DB)
└── test_url.py          # URL-specific unit tests and validation
```

### test_health.py — Smoke Tests

Tests that the `/health` endpoint returns `{"status": "ok"}`. Simple pass/fail check that the app starts and the endpoint is reachable.

### test_graceful.py — Unit Tests (Mocked DB)

Tests that every error condition returns clean JSON rather than an HTML traceback or Python exception. Covers:

- `404` for unknown routes and missing resources
- `405` for wrong HTTP methods
- `500` for database connection failures — verified to return `{"error": "internal server error"}` not an HTML stack trace
- All user CRUD endpoints (GET, POST, PUT, DELETE, list, get by ID, get URLs)
- All event endpoints (list, get by ID)
- URL validation edge cases (ftp:// rejected, numeric URL rejected, unknown fields rejected)

All database calls are mocked with `unittest.mock.patch`. No real PostgreSQL connection needed.

### test_integration.py — Integration Tests (Real SQLite DB)

Tests the full request pipeline: HTTP request → route handler → real database write → database read to verify state. Uses SQLite (via Peewee's `DatabaseProxy` swap) so no PostgreSQL instance is required.

Covers:
- `POST /shorten` writes a URL row to the database
- `POST /shorten` creates an Event record with `event_type="created"`
- `GET /<short_code>` returns a 302 redirect to the original URL
- `DELETE /urls/<id>` sets `is_active=False` (soft delete)
- Deleted URL returns 404 on redirect
- `DELETE` creates an Event with `event_type="deleted"`
- `PATCH /urls/<id>` updates the title field in the database
- `PATCH` creates an Event with `event_type="updated"`
- **Full lifecycle test**: create → resolve → update → delete → verify all three event types exist

### test_url.py — URL Unit Tests

Focused tests for the URL routes and the `is_valid_url` helper:

- Valid URL returns 201
- Invalid URLs return 400 (empty string, non-http/https schemes, non-string types)
- Short code collision retry — mocks `URL.create` to raise `IntegrityError` on first N calls, succeeds on N+1
- If all 5 retries exhaust, returns 500
- `GET /urls/<id>` returns 200 for found, 404 for missing
- `DELETE /urls/<id>` returns 200 for found, 404 for missing
- `PATCH /urls/<id>` with `is_active` set to non-boolean returns 400

---

## Test Configuration

### conftest.py — Global Fixtures

A global `autouse` fixture in `conftest.py` runs for every test in the suite. It mocks all Redis cache functions so no Redis connection is attempted:

```python
@pytest.fixture(autouse=True)
def _mock_cache():
    """Disable Redis for all tests — cache is a no-op, no network calls."""
    with contextlib.ExitStack() as stack:
        for mod in ["app.routes.users", "app.routes.url"]:
            stack.enter_context(patch(f"{mod}.get_cache", return_value=None))
            stack.enter_context(patch(f"{mod}.set_cache"))
            stack.enter_context(patch(f"{mod}.delete_cache"))
            stack.enter_context(patch(f"{mod}.delete_cache_pattern"))
        yield
```

`get_cache` returns `None` (simulates a cache miss), all other operations are no-ops. This ensures:
1. Tests run in ~1 second instead of 7+ minutes (no 30s socket timeouts)
2. Tests are deterministic — cache state never bleeds between tests
3. No Redis service needed to run the test suite

### pyproject.toml — pytest Settings

```toml
[tool.pytest.ini_options]
addopts = "--cov=app --cov-report=term-missing --cov-fail-under=50"
testpaths = ["tests"]
```

Every run automatically reports which lines are not covered (`term-missing`) and fails if coverage drops below 50%.

---

## Mocking Strategy

### Mocking the Database (unit tests)

Unit tests mock at the Peewee driver level using two patches:

```python
with patch("peewee.PostgresqlDatabase.connect"), \
     patch("peewee.PostgresqlDatabase.is_closed", return_value=True):
    response = client.get("/urls")
```

- `connect` is a no-op — the app thinks it connected successfully
- `is_closed` returning `True` tells Peewee the connection is not open, so `reuse_if_open=True` doesn't skip the (mocked) connect call

For specific route behavior, model methods are mocked individually:

```python
with patch("app.routes.users.User.get_by_id", return_value=mock_user):
    ...
```

This isolates the route handler logic from the database entirely.

### Mocking the Database (integration tests)

Integration tests swap PostgreSQL for SQLite using Peewee's `DatabaseProxy`:

```python
test_db = SqliteDatabase(str(tmp_path / "test.db"))
db.initialize(test_db)  # replaces the PostgreSQL proxy
```

A file-based SQLite database (not `:memory:`) is used because Peewee closes the connection after each request via `teardown_appcontext`. File-based SQLite survives close/reopen cycles; `:memory:` databases are destroyed on close.

The `tmp_path` pytest fixture provides a unique temporary directory per test, so databases never share state between tests.

### Mocking the Alert Manager

`create_app()` starts the background alert manager thread unless `TESTING=True`:

```python
if not app.config.get("TESTING"):
    alert_manager.start()
```

All test fixtures set `app.config["TESTING"] = True`, so no background thread is started and no SMTP connections are attempted during tests.

---

## What Is Not Tested

| Area | Why |
|------|-----|
| Redis cache behavior | Mocked globally — cache is a performance optimization, not business logic |
| Email sending | Requires live SMTP; use `fire_drill.py` to test manually |
| Prometheus metric values | Tested implicitly via `/metrics` and `/prometheus` endpoints in health tests |
| Grafana dashboard | UI-only; no automated tests |
| Bulk CSV import | Not covered; would require test CSV files in `seed/` |

---

## Adding New Tests

1. Add a test function in the appropriate file (or create a new file in `tests/`).
2. Use the `client` fixture for unit tests (mocked DB) or the `integration_client` fixture for integration tests.
3. Redis is automatically mocked via `conftest.py` — you do not need to add cache mocks to new tests.
4. Run `uv run pytest -v` to verify your test passes and coverage hasn't dropped.

### Example: adding a unit test

```python
def test_get_url_found(client):
    mock_url = MagicMock()
    mock_url.id = 1
    mock_url.short_code = "abc123"
    mock_url.original_url = "https://example.com"
    mock_url.is_active = True
    mock_url.created_at = "2024-01-01"
    mock_url.updated_at = "2024-01-01"
    mock_url.user_id = None
    mock_url.title = None

    with patch("peewee.PostgresqlDatabase.connect"), \
         patch("peewee.PostgresqlDatabase.is_closed", return_value=True), \
         patch("app.routes.url.URL.get_by_id", return_value=mock_url):
        response = client.get("/urls/1")

    assert response.status_code == 200
    assert response.get_json()["short_code"] == "abc123"
```

### Example: adding an integration test

```python
def test_create_user_and_assign_url(integration_client, tmp_path):
    # Create a user
    resp = integration_client.post("/users", json={"username": "bob", "email": "bob@example.com"})
    assert resp.status_code == 201
    user_id = resp.get_json()["id"]

    # Create a URL owned by that user
    resp = integration_client.post("/urls", json={
        "original_url": "https://example.com",
        "user_id": user_id,
    })
    assert resp.status_code == 201
    assert resp.get_json()["user_id"] == user_id
```
