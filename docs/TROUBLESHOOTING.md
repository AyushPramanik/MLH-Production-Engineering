# Troubleshooting Guide

## Environment Variables

All variables with defaults can be omitted from `.env` unless you need to override them.

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_NAME` | `hackathon_db` | PostgreSQL database name |
| `DATABASE_HOST` | `localhost` | DB hostname (`db` inside Docker) |
| `DATABASE_PORT` | `5432` | DB port |
| `DATABASE_USER` | `postgres` | DB username |
| `DATABASE_PASSWORD` | `postgres` | DB password |

### Redis Cache

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `localhost` | Redis hostname (`redis` inside Docker) |
| `REDIS_PORT` | `6379` | Redis port |

### Flask Server

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_HOST` | `127.0.0.1` | Interface to bind (`0.0.0.0` inside Docker) |
| `FLASK_PORT` | `5000` | Port to listen on |
| `FLASK_DEBUG` | `false` | Enable debug mode (never in production) |

### Email Alerting

| Variable | Default | Description |
|----------|---------|-------------|
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server hostname |
| `SMTP_PORT` | `587` | SMTP port (587 = STARTTLS) |
| `SMTP_USER` | _(empty)_ | SMTP login username |
| `SMTP_PASSWORD` | _(empty)_ | SMTP password or Gmail App Password |
| `ALERT_EMAIL_FROM` | `SMTP_USER` | Sender address in alert emails |
| `ALERT_EMAIL_TO` | _(empty)_ | Recipient address for alerts |

### Alert Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `ALERT_CHECK_INTERVAL` | `30` | Seconds between alert checks |
| `ALERT_COOLDOWN_SECONDS` | `300` | Min seconds between repeat alerts |
| `ALERT_ERROR_RATE_THRESHOLD` | `0.10` | Error rate fraction that triggers alert (0.10 = 10%) |
| `ALERT_MIN_REQUESTS` | `5` | Minimum requests in window before error-rate alert can fire |

---

## Bugs Hit During Development and How We Fixed Them

### Bug 1: `test_create_user` returned 409 instead of 201

**Symptom:** Creating the same user twice returned `409 Conflict` instead of the expected `201` idempotent response.

**Root cause:** The original code did:
```python
try:
    User.create(username=..., email=...)
except IntegrityError:
    user = User.get(...)  # This line silently fails
```
When PostgreSQL raises `IntegrityError`, it aborts the current transaction. Any subsequent query inside the same `except` block runs in a broken transaction state and raises `DoesNotExist` — which the route handler interpreted as a conflict, returning 409.

**Fix:** Check for the existing user *before* attempting the insert:
```python
existing = User.get_or_none(
    (User.username == data["username"]) & (User.email == data["email"])
)
if existing:
    return jsonify(_user_dict(existing)), 201
User.create(username=..., email=...)
```

**Lesson:** Never query inside an `except IntegrityError` block with PostgreSQL — the transaction is already aborted. Validate state before writing, not after catching the failure.

---

### Bug 2: Tests took 7+ minutes to run

**Symptom:** Running `uv run pytest` took 7.5 minutes for 58 tests.

**Root cause:** The Redis client had no connection timeout. Every test that exercised a cached route tried to connect to Redis (which wasn't running), and Python's default socket timeout is ~30 seconds. Across hundreds of cache calls, this multiplied to minutes of hanging.

**Fix (short-term):** Added `socket_connect_timeout=1, socket_timeout=1` to the Redis client in `app/cache.py` so it fails fast.

**Fix (permanent):** Added a `conftest.py` fixture that mocks all Redis calls for every test — no network calls at all:
```python
@pytest.fixture(autouse=True)
def _mock_cache():
    with contextlib.ExitStack() as stack:
        for mod in ["app.routes.users", "app.routes.url"]:
            stack.enter_context(patch(f"{mod}.get_cache", return_value=None))
            stack.enter_context(patch(f"{mod}.set_cache"))
            stack.enter_context(patch(f"{mod}.delete_cache"))
            stack.enter_context(patch(f"{mod}.delete_cache_pattern"))
        yield
```

**Result:** Tests went from 7.5 minutes → 1.08 seconds.

**Lesson:** Always mock external services in unit tests. Use `autouse=True` to ensure the mock applies everywhere without remembering to add it to each test.

---

### Bug 3: Evaluation sandbox couldn't find test results

**Symptom:** The evaluation platform reported: `Could not find the file /test-suite/results.json in container sandbox-*`

**Root cause:** The sandbox started running tests before Flask finished initializing. Flask takes ~10 seconds to establish its first database connection and start the background alert manager. With no healthcheck on the `web` service, the sandbox assumed the container was ready as soon as it started — and the test runner crashed before writing results.

**Fix:** Added a healthcheck to the `web` service in `docker-compose.yml`:
```yaml
healthcheck:
  test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:5000/health')\""]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 10s
```

This makes Docker report the container as unhealthy until `/health` returns 200, so dependent services (and the sandbox) wait for genuine readiness.

**Lesson:** Always add healthchecks to your app container. A running container is not the same as a ready container.

---

### Bug 4: `/dashboard` returned 404

**Symptom:** After adding the dashboard endpoint and template, `curl http://localhost:5001/dashboard` returned 404.

**Root cause:** The running container was built from the old image before the dashboard endpoint was added. Docker cached the old build.

**Fix:**
```bash
docker compose up -d --build web
```

The `--build` flag forces Docker to rebuild the image. Without it, `up -d` just restarts the existing container.

**Lesson:** After changing application code, always `--build` when restarting. The cache is your enemy until it isn't.

---

## Common Problems

### App won't start — database connection refused

```
peewee.OperationalError: could not connect to server
```

**Check:** Is the database running?
```bash
docker compose ps db
docker compose logs db --tail=20
```

**Fix:** Start or restart the DB service:
```bash
docker compose up -d db
docker compose restart web   # after DB is healthy
```

---

### App starts but all requests return 500

**Check:** Look at recent logs:
```bash
docker compose logs web --tail=50
curl http://localhost:5001/logs
```

Common causes:
- Database schema out of sync → restart web (it runs `create_tables` on boot)
- Missing environment variable → check `docker compose exec web env`

---

### Redis connection errors in logs

```
redis.exceptions.ConnectionError: Error 111 connecting to localhost:6379
```

**This is non-fatal** — the app degrades gracefully without Redis (every cache miss hits the DB). But performance will be worse.

**Fix:** Start Redis:
```bash
docker compose up -d redis
```

---

### Email alerts not sending

**Check:** Is SMTP configured?
```bash
curl http://localhost:5001/alert-status
# Look for "email_configured": true/false
```

**Check:** Gmail App Passwords require 2FA to be enabled on the account. A regular Gmail password will not work — you must generate an App Password at https://myaccount.google.com/apppasswords.

**Test the alert manually:**
```bash
uv run python fire_drill.py --high-error-rate
```

---

### Grafana shows "No data"

**Check:** Is Prometheus scraping the app?
1. Open http://localhost:9090/targets — the `hackathon-app` target should be `UP`
2. If it shows `DOWN`, check that the web container is healthy: `docker compose ps web`

**Check:** Is the time range correct? Grafana defaults to "Last 1 hour" — switch to "Last 5 minutes" when testing.

---

### Tests fail with import errors

```
ModuleNotFoundError: No module named 'app'
```

**Fix:** Run tests with `uv run pytest` not `python -m pytest`. The `uv run` prefix activates the project's virtual environment.

---

### Short code redirect returns 404

The redirect endpoint (`GET /<short_code>`) only redirects if `is_active=True`. Check:

```bash
curl http://localhost:5001/urls/<id>
# Look for "is_active": false
```

If `is_active` is false, the URL was soft-deleted. Use `PUT /urls/<id>` with `{"is_active": true}` to restore it.
