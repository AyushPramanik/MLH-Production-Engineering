# mlh-pde — Monitoring & Alerting Demo

A compact Flask-based monitoring and alerting demo that demonstrates:

- An `AlertManager` with pluggable notifiers (Discord webhook + email)
- A lightweight `MetricsStore` (sliding-window counts) used for alerting
- Runtime error capture that triggers immediate alerts for unhandled exceptions
- A small dashboard showing Latency, Traffic, Errors and Saturation
- JSON structured logging written to `logs/app.log`

This repository is intended as a demonstrator for incident detection, alerting, and simple operations workflows.

---

## Project Structure

- `app/` — application package (routes, alerting, metrics, models)
- `run.py` — development entrypoint (starts Flask)
- `docker-compose.yml`, `Dockerfile` — containerization helpers
- `logs/app.log` — application logs (JSON)
- `tests/` — pytest tests
- `docs/` — operational and development documentation (this folder)

Key modules:
- `app/alerting.py` — `AlertManager`, `DiscordNotifier`, `EmailNotifier`
- `app/metrics_store.py` — sliding-window metrics snapshot used by alerts
- `app/__init__.py` — application factory, routes and error handling

---

## Features

- Automatic alerts for:
  - Database unreachable (`service_down`)
  - High error rate (`high_error_rate`)
- Manual alert trigger available at `POST /trigger-alert-now` (intended for testing)
- Monitoring endpoints:
  - `GET /metrics` — current metrics snapshot
  - `GET /alert-status` — alert status and thresholds
  - `GET /logs` — recent structured logs
  - `GET /dashboard` — web dashboard (charts)

---

## Quick start (development)

Requirements: Python 3.10+ (see `pyproject.toml` for project metadata)

1. Create and activate a virtualenv

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate
```

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Configure required environment variables (see Configuration)

4. Run locally

```bash
# from repository root
python run.py
```

The app will bind to `127.0.0.1:5000` by default. Use `FLASK_HOST`, `FLASK_PORT`, and `FLASK_DEBUG=true` to change behaviour.

To run with Docker Compose (provided):

```bash
docker compose up --build
```

---

## Configuration (environment variables)

Set the following environment variables in your environment or a `.env` file (example names shown):

- `DISCORD_WEBHOOK_URL` — Discord webhook to receive alerts (optional)
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` — email notifier settings
- `ALERT_EMAIL_FROM`, `ALERT_EMAIL_TO` — email addresses for notifications
- `ALERT_CHECK_INTERVAL`, `ALERT_COOLDOWN_SECONDS`, `ALERT_ERROR_RATE_THRESHOLD`, `ALERT_MIN_REQUESTS` — alert tuning
- Database:
  - `DATABASE_NAME`, `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_USER`, `DATABASE_PASSWORD`
- Flask runtime:
  - `FLASK_DEBUG`, `FLASK_HOST`, `FLASK_PORT`

Sensitive values (webhooks, passwords) should be stored securely; do not commit them to source control.

---

## Alerts & Notifiers

- The `AlertManager` runs in a background thread and checks two conditions:
  - `service_down`: attempts a short Postgres connection; fires and sends an alert when DB is unreachable
  - `high_error_rate`: evaluates a sliding-window error rate from `MetricsStore`
- Notifiers implemented:
  - `DiscordNotifier` (uses `DISCORD_WEBHOOK_URL`)
  - `EmailNotifier` (SMTP)

If a notifier is not configured the manager logs a warning and continues. See `app/alerting.py` for implementation details.

Common alert failure causes:
- `discord_alert_failed` with HTTP 403/404 — invalid or deleted webhook token, wrong URL, or permission issues
- network / DNS errors — machine cannot reach Discord

See `docs/operations.md` for runbook steps to diagnose and resolve notifier failures.

---

## Metrics & Dashboard

- Metrics endpoint `GET /metrics` returns a snapshot used by the dashboard. The dashboard polls this endpoint and renders charts for:
  - Latency (avg/p95 if available)
  - Traffic (requests per second)
  - Errors (count and rate)
  - Saturation (resource-level metrics if available)

Note: latency (p95) collection is a work-in-progress. See `app/metrics_store.py` and `docs/development.md` for implementation notes.

---

## Logs

- Application logs are JSON structured and written to `logs/app.log` by default. Use `tail -f logs/app.log` (or your platform equivalent) to inspect events, including alert delivery attempts and errors.

---

## Development & Testing

Run tests with `pytest`:

```bash
pytest
```

Unit tests live in `tests/`. CI/test configuration is read from `pyproject.toml`.

---

## Troubleshooting

See `docs/operations.md` for a short runbook covering:
- Verifying webhooks and SMTP
- Diagnosing `discord_alert_failed` log entries (403/404/DNS)
- Restart steps and logs

---

## Contributing

Please open issues or pull requests. For code changes, follow the repository style and add tests for new features.

---

If you'd like, I can now:

- Add a short `docs/incident_response.md` that maps the app alerts to PHE-style incident steps (I can fetch PHE guidance if you point me to the exact doc or URL)
- Flesh out latency/p95 implementation and include the design in `docs/development.md`
