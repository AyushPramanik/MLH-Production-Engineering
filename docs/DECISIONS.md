# Architecture Decision Log

Decisions are recorded here so future contributors understand *why* the system is built the way it is, not just *what* it does.

---

## ADR-001: PostgreSQL as the primary database

**Decision:** Use PostgreSQL 16 (via Docker) as the primary database.

**Alternatives considered:** SQLite, MySQL

**Reasoning:**
- SQLite has no connection pooling and no concurrent write support — unsuitable for a multi-threaded Flask app under load.
- PostgreSQL has native support for `ON CONFLICT DO NOTHING` (used in bulk imports), partial indexes, and `pg_isready` for health checks.
- The hackathon template was already scaffolded for PostgreSQL with `psycopg2`.
- PostgreSQL's strict transaction isolation catches bugs that SQLite would silently swallow (see TROUBLESHOOTING.md Bug 1 — IntegrityError in transaction).

**Trade-off:** Heavier than SQLite, requires a running service. Mitigated by Docker Compose, which starts it with one command.

---

## ADR-002: Peewee as the ORM

**Decision:** Use Peewee ORM instead of SQLAlchemy.

**Alternatives considered:** SQLAlchemy, raw psycopg2

**Reasoning:**
- The hackathon template used Peewee — changing it mid-hackathon would break all existing model code.
- Peewee is simpler than SQLAlchemy for straightforward CRUD and small teams. Its API maps directly to SQL with fewer abstractions to learn.
- `DatabaseProxy` pattern makes it easy to swap the database in tests.

**Trade-off:** Peewee has no built-in migration tool (unlike Alembic for SQLAlchemy). Schema changes must be applied manually. Acceptable for a project at this scale.

---

## ADR-003: Redis for caching

**Decision:** Add Redis 7 as an in-memory cache layer.

**Alternatives considered:** In-process dict cache, Memcached

**Reasoning:**
- An in-process dict cache is not shared across multiple replicas. When we scale to 3 web replicas (see `scaling/`), each would have a stale, independent cache — useless for cache invalidation.
- Redis is the industry standard. It supports key expiry (TTL), pattern-based deletion (`SCAN` + `DELETE`), and survives app restarts.
- Memcached lacks pattern deletion, which we need for invalidating list caches after a write (`urls:list:*`).
- **Graceful degradation:** The app works without Redis — every cache function is wrapped in `try/except` that silently passes. Redis is a performance optimization, not a dependency.

**Trade-off:** Another service to run and monitor. Acceptable — it's a single Docker container.

---

## ADR-004: Prometheus + Grafana for metrics (not a hosted SaaS)

**Decision:** Self-host Prometheus and Grafana via Docker Compose.

**Alternatives considered:** Datadog, New Relic, Honeycomb

**Reasoning:**
- Hosted SaaS platforms require API keys, accounts, and outbound internet access — not available in the evaluation sandbox.
- Self-hosting gives full control over what is collected and how long it is retained (configured to 7 days).
- Prometheus + Grafana is the most common open-source observability stack; skills transfer directly to production environments.
- Auto-provisioned datasources and dashboards mean Grafana is fully configured at startup — no manual clicking.

**Trade-off:** We own the storage and availability of our metrics. Mitigated by `restart: always` and Docker volume persistence.

---

## ADR-005: Structured JSON logging instead of plain text

**Decision:** Replace `print()` and default Flask logging with a custom `JSONFormatter`.

**Alternatives considered:** Plain text logs, logfmt

**Reasoning:**
- Plain text logs require regex parsing to extract fields like request duration or status code. Machines cannot query them reliably.
- JSON logs can be ingested directly by log aggregators (Loki, Datadog, Splunk, CloudWatch) without any parsing configuration.
- Every log line includes `timestamp`, `level`, `logger`, `message`, and any `extra={}` fields passed by the caller — fully structured.
- The `/logs` endpoint can serve these records as JSON over HTTP, enabling the dashboard to display them without SSH access.

**Trade-off:** Slightly harder to read raw in the terminal. Mitigated by the `/logs` endpoint and dashboard log viewer.

---

## ADR-006: Background thread for alert manager (not a separate service)

**Decision:** Run the alert manager in a Python daemon thread within the Flask process.

**Alternatives considered:** Separate Celery worker, separate Docker service, cron job

**Reasoning:**
- A Celery worker requires a message broker (RabbitMQ or Redis as a queue) and an additional container — significant complexity for two alert conditions.
- A separate Docker service would need to share the metrics store state. Inter-process communication would require serializing the sliding window to Redis, adding latency and complexity.
- The daemon thread shares memory with the Flask process, so it reads the `MetricsStore` directly — no serialization needed.
- Daemon threads are automatically killed when the main process exits, so no orphaned processes.

**Trade-off:** If the Flask process crashes, alerting stops. Acceptable — if Flask crashes, Docker restarts it within seconds, and the `service_down` alert for the database covers the most critical failure mode.

---

## ADR-007: Soft delete for URLs

**Decision:** `DELETE /urls/<id>` sets `is_active=False` instead of removing the row.

**Alternatives considered:** Hard delete (physical row removal)

**Reasoning:**
- Short codes are 6 characters — once a code is given to a user, hard-deleting it means the code could be reissued to a different URL. Old bookmarks would silently redirect to an unrelated destination.
- Soft delete preserves the audit trail — the Event records for a URL remain meaningful even after deletion.
- Restoration is trivial: `PUT /urls/<id>` with `{"is_active": true}`.

**Trade-off:** The table grows forever. Acceptable at this scale. A cleanup job could hard-delete rows older than N days if needed.

---

## ADR-008: Sliding window (deque) for error rate, not a counter

**Decision:** Use a time-bucketed deque in `MetricsStore` instead of a simple counter or Prometheus query.

**Alternatives considered:** `rate()` in Prometheus, rolling counter with Redis

**Reasoning:**
- Prometheus `rate()` requires Prometheus to be running and adds an HTTP round-trip per check interval. The alert manager lives in the app process — a deque is a direct memory read.
- A simple counter without a time window would trigger on the total error rate since startup, not the recent rate. A single error at boot could keep the alert firing indefinitely.
- A deque evicts entries older than 120 seconds naturally as new entries are added, requiring no scheduled cleanup.
- Thread-safe with a `Lock` — safe under concurrent Flask workers.

**Trade-off:** State is in-process memory only. Restarting the app resets the window. Acceptable — the purpose is detecting *current* problems, not historical trends (Prometheus handles history).

---

## ADR-009: uv as the package manager

**Decision:** Use `uv` instead of `pip` + `venv`.

**Alternatives considered:** pip, pipenv, Poetry

**Reasoning:**
- `uv` is 10–100x faster than pip for dependency resolution and installation — critical in a Docker build where every second counts.
- `uv sync` installs exact versions from `pyproject.toml` without a separate lockfile command.
- `uv run <script>` activates the venv automatically — developers don't need to source activate scripts.
- The hackathon template already used `uv`.

**Trade-off:** Less widely known than pip. Mitigated by the README explaining the basic commands.
