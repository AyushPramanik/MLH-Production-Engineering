# MLH PE Hackathon — URL Shortener + Observability Platform

A production-grade URL shortener with full observability: structured logging, Prometheus metrics, Grafana dashboards, Redis caching, and email alerting.

**Stack:** Flask · Peewee ORM · PostgreSQL 16 · Redis 7 · Prometheus · Grafana · Docker Compose

---

## Architecture

```
                        ┌─────────────────────────────────────────┐
                        │            Docker Compose Network        │
                        │                                         │
  Browser / Client ─────┤──► web (Flask :5000) ──► db (Postgres) │
       :5001             │         │    │                         │
                        │         │    └──────► redis (:6379)    │
  Grafana :3000 ◄───────┤         │                              │
                        │         ▼                               │
  Prometheus :9090 ◄────┤──► /prometheus  (metrics scrape)       │
                        │                                         │
                        └─────────────────────────────────────────┘

  Request flow:
  Client → Flask before_request (timing start, DB connect)
         → Route handler (cache check → DB query → cache write)
         → Flask after_request (record metrics, log JSON)
         → Response
```

---

## Prerequisites

- **Docker Desktop** (includes Docker Compose) — [install](https://docs.docker.com/get-docker/)
- **uv** (for local development without Docker):
  ```bash
  # macOS / Linux
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

---

## Quick Start (Docker — recommended)

```bash
# 1. Clone the repo
git clone <repo-url> && cd mlh-pe-hackathon

# 2. Start everything (app + DB + Redis + Prometheus + Grafana)
docker compose up -d

# 3. Wait ~15 seconds for services to be healthy, then verify
curl http://localhost:5001/health
# → {"status": "ok", "hostname": "..."}

# 4. (Optional) Seed with sample data
docker compose exec web uv run python seed/seed.py

# 5. Open the monitoring dashboard
open http://localhost:5001/dashboard   # built-in live dashboard
open http://localhost:3000             # Grafana (admin / admin)
open http://localhost:9090             # Prometheus
```

That's it — the entire stack runs with one command.

---

## Quick Start (Local Development)

```bash
# 1. Install dependencies
uv sync

# 2. Start only the backing services
docker compose up -d db redis

# 3. Configure environment
cp .env.example .env
# Edit .env if your DB credentials differ from the defaults

# 4. Run the Flask server
uv run run.py

# 5. Verify
curl http://localhost:5000/health
```

---

## Running Tests

```bash
uv run pytest
```

Tests mock Redis and run against a real PostgreSQL database. Coverage must stay above 50%.

---

## Project Structure

```
mlh-pe-hackathon/
├── app/
│   ├── __init__.py          # App factory, middleware, system routes
│   ├── database.py          # Peewee ORM setup and connection hooks
│   ├── cache.py             # Redis client and get/set/delete helpers
│   ├── alerting.py          # Background email alert manager
│   ├── prometheus_metrics.py # Prometheus counter/histogram/gauge definitions
│   ├── metrics_store.py     # Thread-safe sliding-window error tracker
│   ├── logging_config.py    # Structured JSON logging setup
│   ├── models/              # Peewee data models (User, URL, Event)
│   ├── routes/              # Blueprint route handlers
│   │   ├── users.py         # User CRUD + bulk load
│   │   ├── url.py           # URL shortener CRUD + redirect
│   │   └── events.py        # Audit log queries
│   └── templates/
│       └── dashboard.html   # Self-contained live monitoring dashboard
├── docs/
│   ├── RUNBOOK.md           # Incident response playbooks
│   ├── DEPLOY.md            # Deployment and rollback guide
│   ├── TROUBLESHOOTING.md   # Common problems and fixes
│   ├── DECISIONS.md         # Architecture decision log
│   └── CAPACITY.md          # Capacity planning and limits
├── monitoring/
│   ├── prometheus.yml       # Scrape config
│   └── grafana/provisioning # Auto-provisioned datasource + dashboard
├── scaling/
│   ├── nginx/nginx.conf     # Load balancer config (multi-replica)
│   └── load_test/           # k6 and Python load test scripts
├── seed/
│   ├── seed.py              # Database seeding script
│   └── *.csv                # Sample data files
├── tests/                   # pytest test suite
├── docker-compose.yml       # Full stack orchestration
├── Dockerfile               # App container (python:3.13-slim + uv)
├── pyproject.toml           # Dependencies and pytest config
├── .env.example             # All environment variables documented
└── fire_drill.py            # Alert testing tool (safe, no real incidents needed)
```

---

## API Reference

All endpoints return JSON. Errors follow `{"error": "<message>"}`.

### System

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check — returns `{"status":"ok","hostname":"..."}` |
| GET | `/metrics` | JSON system metrics — CPU%, memory MB, request counts |
| GET | `/prometheus` | Prometheus scrape endpoint (text/plain exposition format) |
| GET | `/logs?limit=100` | Recent application log entries as JSON array |
| GET | `/alert-status` | Current alert states (service_down, high_error_rate) |
| GET | `/dashboard` | Live monitoring dashboard (HTML) |

### Users

| Method | Path | Description |
|--------|------|-------------|
| GET | `/users?page=1&per_page=20` | List users (paginated, cached) |
| POST | `/users` | Create user — body: `{"username":"…","email":"…"}` |
| GET | `/users/<id>` | Get user by ID (cached) |
| PUT | `/users/<id>` | Update username/email |
| DELETE | `/users/<id>` | Hard delete user |
| GET | `/users/<id>/urls` | All URLs belonging to a user |
| POST | `/users/bulk` | Bulk import from CSV — body: `{"file":"users.csv"}` |

### URLs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/urls?user_id=&is_active=&page=1&per_page=20` | List URLs (filtered, cached) |
| POST | `/urls` | Create short URL — body: `{"original_url":"…","title":"…","user_id":1}` |
| POST | `/shorten` | Alias for POST /urls — body: `{"url":"…"}` |
| GET | `/urls/<id>` | Get URL by ID (cached) |
| PUT/PATCH | `/urls/<id>` | Update URL fields |
| DELETE | `/urls/<id>` | Soft delete (sets `is_active=false`) |
| GET | `/urls/<id>/events` | Audit log for a URL |
| POST | `/urls/bulk` | Bulk import from CSV — body: `{"file":"urls.csv"}` |
| GET | `/<short_code>` | Redirect to original URL (302) |

### Events

| Method | Path | Description |
|--------|------|-------------|
| GET | `/events?url_id=&user_id=&event_type=` | List events (filtered) |
| POST | `/events` | Create event — body: `{"url_id":1,"event_type":"created"}` |
| GET | `/events/<id>` | Get event by ID |

### Response shapes

**User object:**
```json
{"id": 1, "username": "alice", "email": "alice@example.com", "created_at": "2024-01-01T12:00:00"}
```

**URL object:**
```json
{
  "id": 1, "user_id": 1, "short_code": "abc123",
  "original_url": "https://example.com", "title": "Example",
  "is_active": true, "created_at": "…", "updated_at": "…"
}
```

**Event object:**
```json
{"id": 1, "url_id": 1, "user_id": 1, "event_type": "created", "timestamp": "…", "details": "…"}
```

---

## Monitoring URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| App | http://localhost:5001 | — |
| Live Dashboard | http://localhost:5001/dashboard | — |
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | — |

---

## Alerting (Email)

Copy `.env.example` to `.env` and fill in the SMTP section to enable email alerts:

```bash
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-app-password   # Gmail App Password (not your login password)
ALERT_EMAIL_TO=oncall@yourteam.com
```

Two alerts fire automatically:
- **Service Down** — PostgreSQL unreachable
- **High Error Rate** — >10% of requests return 5xx in a 2-minute window

See [`docs/RUNBOOK.md`](docs/RUNBOOK.md) for response playbooks.

---

## Error Handling

| Status | Meaning |
|--------|---------|
| 200 / 201 | Success |
| 302 | Redirect (short URL) |
| 400 | Bad request — validation failed (see `"error"` field) |
| 404 | Resource not found or inactive |
| 405 | Wrong HTTP method |
| 409 | Conflict — duplicate username or email |
| 500 | Unexpected server error (never an HTML stack trace) |

---

## Further Reading

- [`docs/DEPLOY.md`](docs/DEPLOY.md) — how to deploy and rollback
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — common problems and fixes
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — why we chose each technology
- [`docs/CAPACITY.md`](docs/CAPACITY.md) — how many users can we handle
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — incident response playbooks
