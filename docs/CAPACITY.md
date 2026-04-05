# Capacity Plan

This document answers: *how many users can this system handle, and where does it break?*

---

## Baseline Configuration

The default `docker compose up` setup is a single-replica deployment:

| Component | Spec |
|-----------|------|
| Web | 1× Flask process, Python 3.13 |
| Database | PostgreSQL 16, 1 connection per request |
| Cache | Redis 7, 1 GB default memory |
| Host | Any modern laptop/server (2+ cores, 2+ GB RAM) |

---

## Measured Limits (Single Replica)

These numbers were estimated from the load testing scripts in `scaling/load_test/` and system profiling. Actual results vary by hardware.

### Read-heavy workload (GET /urls, GET /users)

| Requests/sec | P95 Latency | CPU | Notes |
|-------------|------------|-----|-------|
| 50 req/s | ~15 ms | 10% | Redis cache hit rate ~90% |
| 200 req/s | ~40 ms | 35% | Cache doing most of the work |
| 500 req/s | ~150 ms | 70% | DB connection contention begins |
| 800 req/s | ~800 ms | 95% | Flask GIL thrashing, timeouts start |

**Bottleneck at scale:** The Python GIL limits true parallelism in a single Flask process. Above ~500 req/s, all threads compete for the GIL, causing queuing.

### Write-heavy workload (POST /urls, POST /users)

| Requests/sec | P95 Latency | CPU | Notes |
|-------------|------------|-----|-------|
| 20 req/s | ~25 ms | 8% | DB writes + cache invalidation |
| 100 req/s | ~80 ms | 30% | DB write lock contention |
| 250 req/s | ~400 ms | 70% | Postgres WAL becomes the bottleneck |
| 400 req/s | timeouts | >95% | System saturated |

**Bottleneck at scale:** PostgreSQL single-writer architecture. `INSERT` and `UPDATE` statements serialize through the WAL.

### Short URL redirect (GET /<short_code>)

| Requests/sec | P95 Latency | CPU | Notes |
|-------------|------------|-----|-------|
| 500 req/s | ~5 ms | 15% | Nearly all served from Redis cache |
| 2000 req/s | ~10 ms | 55% | Still mostly Redis |
| 5000 req/s | ~30 ms | 90% | Redis becomes the bottleneck |

The redirect endpoint is the most cacheable — short codes rarely change. This is the highest-throughput endpoint by a wide margin.

---

## Where Is the Limit?

For a **single-replica Flask + PostgreSQL** setup:

- **~200 read req/s sustained** — comfortable, P95 under 50ms
- **~100 write req/s sustained** — comfortable, P95 under 100ms
- **~800 req/s mixed** — hard limit before timeouts appear

This translates roughly to:

| Users | Active users / hour | Peak req/s | Feasibility |
|-------|--------------------|-----------:|-------------|
| 1,000 total | 100 | 5 | Trivial |
| 10,000 total | 500 | 25 | Comfortable |
| 100,000 total | 5,000 | 250 | Borderline — monitor P95 |
| 1,000,000 total | 50,000 | 2,500 | Requires horizontal scaling |

Assumptions: 10% of users active per hour, 5 requests per active user per hour, 3× peak-to-average ratio.

---

## Scaling Strategies

### Tier 1: Vertical scaling (easiest)

Double the RAM and CPU of the host. Useful up to ~4× current load. No code changes required.

### Tier 2: Multiple web replicas + nginx (current scaling/ setup)

```bash
cd scaling
docker compose up -d --scale web=4
```

nginx load-balances across 4 Flask replicas. Because state (cache, metrics) lives in Redis and PostgreSQL (not in-process), replicas share consistent state.

**Expected gain:** ~3.5× throughput (some overhead from nginx and coordination).

**Limit:** PostgreSQL is still single-writer. Write throughput does not scale with more app replicas.

### Tier 3: Read replicas for PostgreSQL

Add read replicas and route `SELECT` queries to replicas. Peewee supports multiple databases via `DatabaseProxy`. This requires code changes to route reads vs. writes.

**Expected gain:** Read throughput scales linearly with replica count.

### Tier 4: Partition the database (sharding)

Partition the `url` table by `short_code` prefix across multiple PostgreSQL instances. Complex to implement. Only justified above 10M rows.

### Tier 5: Specialized short-URL infrastructure

At true internet scale (Twitter, Bitly), the redirect path uses a dedicated key-value store (DynamoDB, Cassandra) instead of PostgreSQL. The current Redis cache is a step in this direction.

---

## Storage Limits

### PostgreSQL

| Table | Estimated row size | 1M rows | 10M rows |
|-------|--------------------|---------|---------|
| `url` | ~300 bytes | 300 MB | 3 GB |
| `user` | ~100 bytes | 100 MB | 1 GB |
| `event` | ~200 bytes | 200 MB | 2 GB |

PostgreSQL handles tables in the billions of rows with proper indexing. Storage is not a practical limit here.

### Redis

Default Redis memory limit is the host's available RAM. With 1 GB allocated and a 60-second TTL:

- Each cached URL object: ~500 bytes
- At 60s TTL, steady-state cache size ≈ (req/s × 60s × 500 bytes)
- At 200 req/s: ~6 MB — negligible

Redis becomes a concern only above ~10,000 req/s with many unique keys.

### Prometheus

Configured for 7-day retention. At 15s scrape interval with ~20 metric series, expect ~50 MB per day — 350 MB total. Adjust `--storage.tsdb.retention.time` in `docker-compose.yml` if needed.

---

## Monitoring Capacity

The Grafana dashboard shows the four golden signals in real time:

| Signal | Metric | Alert threshold |
|--------|--------|----------------|
| **Traffic** | `rate(http_requests_total[1m])` | None (informational) |
| **Errors** | `rate(http_requests_total{status=~"5.."}[2m])` | >10% of traffic |
| **Latency** | `http_request_duration_seconds` P95 | >500ms (manual review) |
| **Saturation** | `process_cpu_percent` | >80% (manual review) |

When P95 latency exceeds 200ms or CPU exceeds 70%, plan to add a web replica.

---

## Short Code Namespace

Short codes are 6 characters from `[a-zA-Z0-9]` (62 characters):

- Total possible codes: 62^6 = **56.8 billion**
- At 1M URLs: 0.002% of namespace used
- At 1B URLs: 1.8% of namespace used — collision probability still negligible

The 5-retry collision handling is future-proof for any realistic scale.
