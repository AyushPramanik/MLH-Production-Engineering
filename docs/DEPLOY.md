# Deploy Guide

## Prerequisites

- Docker and Docker Compose installed on the target server
- Git access to the repository
- A `.env` file with production credentials (see [CONFIG section in TROUBLESHOOTING.md](TROUBLESHOOTING.md))

---

## First-Time Deployment

```bash
# 1. Clone the repository
git clone <repo-url>
cd mlh-pe-hackathon

# 2. Create and configure the environment file
cp .env.example .env
# Edit .env — set DATABASE_PASSWORD, SMTP credentials, ALERT_EMAIL_TO

# 3. Build and start all services
docker compose up -d --build

# 4. Verify all services are healthy
docker compose ps
# All services should show "(healthy)" or "Up"

# 5. Check the app is responding
curl http://localhost:5001/health
# → {"status": "ok", "hostname": "..."}

# 6. (Optional) Seed initial data
docker compose exec web uv run python seed/seed.py
```

The full stack (app + PostgreSQL + Redis + Prometheus + Grafana) starts in a single command. Services wait for their dependencies to be healthy before starting (configured via `depends_on: condition: service_healthy`).

---

## Deploying an Update

```bash
# 1. Pull the latest code
git pull origin main

# 2. Rebuild and restart only the app container (zero downtime for DB/cache/monitoring)
docker compose up -d --build web

# 3. Verify the new version is running
curl http://localhost:5001/health
docker compose logs web --tail=20
```

The `--build` flag rebuilds the image from the latest code. `up -d` replaces the running container without touching the database, Redis, Prometheus, or Grafana containers.

---

## Rollback

### Option 1: Roll back via git (recommended)

```bash
# Find the last known-good commit
git log --oneline -10

# Check out the previous commit
git checkout <good-commit-hash>

# Rebuild and restart
docker compose up -d --build web

# Verify
curl http://localhost:5001/health
```

### Option 2: Roll back using a Docker image tag

If you tag images on each deploy:

```bash
# Retag the previous image as latest
docker tag mlh-pe-hackathon-web:<previous-tag> mlh-pe-hackathon-web:latest

# Restart the web container (no rebuild needed)
docker compose up -d web
```

---

## Zero-Downtime Deployment (Multi-Replica)

The `scaling/` directory contains an nginx-fronted multi-replica setup for zero-downtime deploys:

```bash
# Start with 3 web replicas behind nginx
cd scaling
docker compose up -d --scale web=3

# Rolling update: rebuild and restart one replica at a time
docker compose up -d --build --no-deps web
```

nginx is configured with upstream health checks, so it stops routing to a replica while it restarts.

---

## Database Migrations

Peewee uses `create_tables(safe=True)` on startup, which creates tables if they don't exist but does not alter existing ones. For schema changes:

```bash
# Connect to the running database
docker compose exec db psql -U postgres hackathon_db

# Run your ALTER TABLE statements manually
ALTER TABLE url ADD COLUMN clicks INTEGER DEFAULT 0;
\q

# Restart the app to pick up any model changes
docker compose restart web
```

There is no automated migration tool. Document every schema change in the commit message.

---

## Stopping the Stack

```bash
# Stop containers but keep data volumes
docker compose down

# Stop AND delete all data (destructive — use only in dev)
docker compose down -v
```

Data is stored in named Docker volumes (`postgres_data`, `redis_data`, `prometheus_data`, `grafana_data`). These survive `docker compose down` but are deleted by `docker compose down -v`.

---

## Backup

### PostgreSQL

```bash
# Dump the database to a file
docker compose exec db pg_dump -U postgres hackathon_db > backup_$(date +%Y%m%d).sql

# Restore from a dump
cat backup_20240101.sql | docker compose exec -T db psql -U postgres hackathon_db
```

### Prometheus metrics

Prometheus stores 7 days of metrics in the `prometheus_data` volume. To export:

```bash
docker run --rm -v mlh-pe-hackathon_prometheus_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/prometheus_backup.tar.gz /data
```

---

## Environment-Specific Configuration

| Setting | Development | Production |
|---------|-------------|------------|
| `FLASK_DEBUG` | `true` | `false` |
| `DATABASE_PASSWORD` | `postgres` | Strong random password |
| `SMTP_PASSWORD` | (empty, alerts disabled) | Gmail App Password |
| `ALERT_COOLDOWN_SECONDS` | `60` | `300` |
| Grafana password | `admin` | Change on first login |

In production, set `GF_SECURITY_ADMIN_PASSWORD` in `docker-compose.yml` to something other than `admin`.

---

## Health Checks

All services expose health checks to Docker Compose:

| Service | Check | Interval |
|---------|-------|----------|
| web | `GET /health` returns 200 | 10s |
| db | `pg_isready` | 5s |
| redis | `redis-cli PING` | 5s |

Use `docker compose ps` to see current health status. Grafana at http://localhost:3000 shows live metrics.
