# API Documentation

Base URL: `http://localhost:5001`  
All request and response bodies are JSON unless noted otherwise.  
All error responses follow the shape: `{"error": "<message>"}`.

---

## Table of Contents

- [System](#system)
- [Users](#users)
- [URLs](#urls)
- [Events](#events)
- [Status Codes](#status-codes)

---

## System

### GET /health

Health check. Used by load balancers and Docker healthchecks.

**Response 200**
```json
{
  "status": "ok",
  "hostname": "e356af23bf9a"
}
```

---

### GET /metrics

System metrics snapshot in JSON format.

**Response 200**
```json
{
  "cpu_percent": 4.2,
  "memory": {
    "total_mb": 8192.0,
    "used_mb": 3100.5,
    "available_mb": 5091.5,
    "percent": 37.8
  },
  "requests": {
    "total": 142,
    "errors": 3,
    "error_rate": 0.0211,
    "window_seconds": 120
  },
  "hostname": "e356af23bf9a"
}
```

`requests` reflects a sliding 2-minute window.

---

### GET /prometheus

Prometheus scrape endpoint. Returns metrics in Prometheus exposition text format.

**Response 200** — `Content-Type: text/plain; version=0.0.4`
```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{endpoint="/health",method="GET",status="200"} 5.0
...
```

Scraped automatically by Prometheus every 15 seconds. Not intended for direct human use — use `/metrics` or Grafana instead.

---

### GET /logs

Recent application log entries.

**Query parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | `100` | Max number of log lines to return |

**Response 200**
```json
[
  {
    "timestamp": "2024-01-01T12:00:00.000Z",
    "level": "INFO",
    "logger": "app",
    "message": "request",
    "method": "GET",
    "path": "/health",
    "status": 200,
    "duration_ms": 1.23,
    "remote_addr": "127.0.0.1"
  }
]
```

Returns an empty array `[]` if no log file exists yet.

---

### GET /alert-status

Current state of all configured alerts.

**Response 200**
```json
{
  "service_down": {
    "firing": false,
    "last_fired": null
  },
  "high_error_rate": {
    "firing": false,
    "last_fired": null
  }
}
```

**Response 503** — if the alert manager is not running.

---

### GET /dashboard

Live monitoring dashboard (HTML). Opens in the browser.

**Response 200** — `Content-Type: text/html`

Displays real-time graphs for the 4 golden signals (Traffic, Errors, Latency, Saturation), alert status, and recent logs. Auto-refreshes every 10 seconds.

---

## Users

### GET /users

List all users. Results are cached for 60 seconds per unique query.

**Query parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | — | Page number (requires `per_page`) |
| `per_page` | integer | — | Results per page (requires `page`) |

**Response 200**
```json
[
  {
    "id": 1,
    "username": "alice",
    "email": "alice@example.com",
    "created_at": "2024-01-01T12:00:00"
  }
]
```

---

### POST /users

Create a new user. Idempotent — if the exact `username` + `email` combination already exists, returns the existing user with `201`.

**Request body**
```json
{
  "username": "alice",
  "email": "alice@example.com"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | Yes | Must be unique |
| `email` | string | Yes | Must be unique |

**Response 201**
```json
{
  "id": 1,
  "username": "alice",
  "email": "alice@example.com",
  "created_at": "2024-01-01T12:00:00"
}
```

**Errors**

| Status | Body | Cause |
|--------|------|-------|
| 400 | `{"error": "username and email are required"}` | Missing field |
| 409 | `{"error": "username or email already exists"}` | Duplicate with different email or username |

---

### GET /users/:id

Get a single user by ID. Cached for 60 seconds.

**Response 200**
```json
{
  "id": 1,
  "username": "alice",
  "email": "alice@example.com",
  "created_at": "2024-01-01T12:00:00"
}
```

**Errors**

| Status | Body | Cause |
|--------|------|-------|
| 404 | `{"error": "user not found"}` | ID does not exist |

---

### PUT /users/:id

Update a user's username and/or email.

**Request body** (all fields optional, at least one required)
```json
{
  "username": "bob",
  "email": "bob@example.com"
}
```

**Response 200** — updated user object

**Errors**

| Status | Body | Cause |
|--------|------|-------|
| 400 | `{"error": "no valid fields to update"}` | Empty or unrecognised body |
| 404 | `{"error": "user not found"}` | ID does not exist |
| 409 | `{"error": "username or email already exists"}` | Conflict with another user |

---

### DELETE /users/:id

Hard delete a user. Removes the row permanently.

**Response 200**
```json
{"message": "deleted"}
```

**Errors**

| Status | Body | Cause |
|--------|------|-------|
| 404 | `{"error": "user not found"}` | ID does not exist |

---

### GET /users/:id/urls

List all URLs belonging to a user.

**Response 200** — array of URL objects (see [URL object](#url-object))

**Errors**

| Status | Body | Cause |
|--------|------|-------|
| 404 | `{"error": "user not found"}` | User ID does not exist |

---

### POST /users/bulk

Bulk import users from a CSV file in the `seed/` directory.

**Request body**
```json
{
  "file": "users.csv"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `file` | string | `"users.csv"` | Filename inside the `seed/` directory |

CSV must have columns: `username`, `email`. Additional columns (e.g. `id`, `created_at`) are ignored.  
Duplicate usernames or emails are silently skipped (`ON CONFLICT DO NOTHING`).

**Response 201**
```json
{"imported": 400}
```

`imported` is the count of rows read from the CSV, not the count actually inserted.

**Errors**

| Status | Body | Cause |
|--------|------|-------|
| 400 | `{"error": "invalid filename"}` | Path traversal attempt or non-CSV file |
| 404 | `{"error": "users.csv not found"}` | File not in `seed/` directory |

---

## URLs

### URL Object

All URL endpoints return objects with this shape:

```json
{
  "id": 1,
  "user_id": 1,
  "short_code": "abc123",
  "original_url": "https://example.com",
  "title": "Example Site",
  "is_active": true,
  "created_at": "2024-01-01T12:00:00",
  "updated_at": "2024-01-01T12:00:00"
}
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | integer | Auto-assigned primary key |
| `user_id` | integer \| null | Owner (optional) |
| `short_code` | string | 6 alphanumeric characters |
| `original_url` | string | Must be `http://` or `https://` |
| `title` | string \| null | Optional human-readable label |
| `is_active` | boolean | `false` = soft-deleted, redirect returns 404 |
| `created_at` | string | ISO 8601 |
| `updated_at` | string | ISO 8601 |

---

### GET /urls

List URLs with optional filtering. Cached per unique query combination.

**Query parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `user_id` | integer | — | Filter by owner |
| `is_active` | `true` \| `false` | — | Filter by active status |
| `page` | integer | — | Page number (requires `per_page`) |
| `per_page` | integer | — | Results per page (requires `page`) |

**Response 200** — array of URL objects

---

### POST /urls

Create a short URL.

**Request body**
```json
{
  "original_url": "https://example.com",
  "title": "Example",
  "user_id": 1
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `original_url` | string | Yes | Must start with `http://` or `https://` |
| `title` | string | No | Human-readable label |
| `user_id` | integer | No | Associate with a user |

**Response 201** — URL object with generated `short_code`

**Errors**

| Status | Body | Cause |
|--------|------|-------|
| 400 | `{"error": "original_url is required"}` | Missing field |
| 400 | `{"error": "invalid url"}` | Non-http/https or malformed URL |
| 500 | `{"error": "could not generate unique short code"}` | Extremely rare collision after 5 retries |

---

### POST /shorten

Legacy alias for `POST /urls`. Accepts `url` instead of `original_url`.

**Request body**
```json
{
  "url": "https://example.com",
  "title": "Example",
  "user_id": 1
}
```

**Response 201**
```json
{
  "short_code": "abc123",
  "original_url": "https://example.com"
}
```

**Errors** — same as `POST /urls` but field name is `url`.

---

### GET /urls/:id

Get a URL by its numeric ID. Cached for 60 seconds.

**Response 200** — URL object

**Errors**

| Status | Body | Cause |
|--------|------|-------|
| 404 | `{"error": "url not found"}` | ID does not exist |

---

### PUT /urls/:id  &  PATCH /urls/:id

Update a URL. Both methods are equivalent.

**Request body** (all fields optional, at least one required)
```json
{
  "original_url": "https://new-url.com",
  "title": "New Title",
  "is_active": false,
  "user_id": 2
}
```

| Field | Type | Description |
|-------|------|-------------|
| `original_url` | string | Must be valid http/https URL |
| `title` | string | Human-readable label |
| `is_active` | boolean | Set to `false` to soft-delete, `true` to restore |
| `user_id` | integer | Reassign ownership (recorded in event only) |

Creates an audit Event with `event_type="updated"`.

**Response 200** — updated URL object

**Errors**

| Status | Body | Cause |
|--------|------|-------|
| 400 | `{"error": "invalid url"}` | `original_url` fails validation |
| 400 | `{"error": "is_active must be a boolean"}` | Non-boolean `is_active` value |
| 400 | `{"error": "no valid fields to update"}` | No recognised fields in body |
| 404 | `{"error": "url not found"}` | ID does not exist |

---

### DELETE /urls/:id

Soft delete a URL. Sets `is_active=false` — the row is preserved but the redirect returns 404.

Creates an audit Event with `event_type="deleted"`.

**Response 200**
```json
{"message": "deleted"}
```

**Errors**

| Status | Body | Cause |
|--------|------|-------|
| 404 | `{"error": "url not found"}` | ID does not exist |

To restore a soft-deleted URL: `PATCH /urls/:id` with `{"is_active": true}`.

---

### GET /urls/:id/events

Audit log for a specific URL. Returns all events in insertion order.

**Response 200** — array of Event objects (see [Event Object](#event-object))

**Errors**

| Status | Body | Cause |
|--------|------|-------|
| 404 | `{"error": "url not found"}` | URL ID does not exist |

---

### POST /urls/bulk

Bulk import URLs from a CSV file in the `seed/` directory.

**Request body**
```json
{
  "file": "urls.csv"
}
```

CSV must have columns: `short_code`, `original_url`. Optional columns: `user_id`, `title`, `is_active`, `created_at`, `updated_at`.  
Duplicate `short_code` values are silently skipped.

**Response 201**
```json
{"imported": 400}
```

**Errors**

| Status | Body | Cause |
|--------|------|-------|
| 400 | `{"error": "invalid filename"}` | Path traversal or non-CSV |
| 404 | `{"error": "urls.csv not found"}` | File not in `seed/` directory |

---

### GET /:short_code

Redirect to the original URL.

**Response 302** — `Location` header set to `original_url`

**Errors**

| Status | Body | Cause |
|--------|------|-------|
| 404 | `{"error": "not found"}` | Code not in DB, or URL has `is_active=false` |

---

## Events

### Event Object

```json
{
  "id": 1,
  "url_id": 1,
  "user_id": 1,
  "event_type": "created",
  "timestamp": "2024-01-01T12:00:00",
  "details": {"short_code": "abc123", "original_url": "https://example.com"}
}
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | integer | Auto-assigned primary key |
| `url_id` | integer | The URL this event belongs to |
| `user_id` | integer \| null | User who triggered the event (optional) |
| `event_type` | string | `"created"`, `"updated"`, `"deleted"`, or custom |
| `timestamp` | string | ISO 8601 |
| `details` | object \| string \| null | Parsed JSON if valid, raw string otherwise |

Events are immutable — they are never updated or deleted.

---

### GET /events

List events with optional filters. No pagination, no caching.

**Query parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `url_id` | integer | Filter by URL |
| `user_id` | integer | Filter by user |
| `event_type` | string | Filter by type (e.g. `"created"`) |

**Response 200** — array of Event objects

---

### POST /events

Create an event manually.

**Request body**
```json
{
  "url_id": 1,
  "event_type": "viewed",
  "user_id": 2,
  "details": {"ip": "192.168.1.1"}
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url_id` | integer | Yes | Must reference an existing URL |
| `event_type` | string | Yes | Any string label |
| `user_id` | integer | No | Associated user |
| `details` | object \| string | No | Arbitrary metadata; objects are serialised to JSON |

**Response 201** — Event object

**Errors**

| Status | Body | Cause |
|--------|------|-------|
| 400 | `{"error": "event_type and url_id are required"}` | Missing required fields |
| 400 | `{"error": "invalid url_id or constraint violation"}` | `url_id` references a non-existent URL |

---

### GET /events/:id

Get a single event by ID.

**Response 200** — Event object

**Errors**

| Status | Body | Cause |
|--------|------|-------|
| 404 | `{"error": "not found"}` | ID does not exist |

---

## Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 302 | Redirect (short URL resolution) |
| 400 | Bad request — validation failed |
| 404 | Resource not found or inactive |
| 405 | Method not allowed |
| 409 | Conflict — duplicate unique field |
| 500 | Unexpected server error |
| 503 | Service unavailable (alert manager not running) |

---

## Example: Full URL Lifecycle

```bash
# Create a user
curl -X POST http://localhost:5001/users \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "email": "alice@example.com"}'
# → {"id": 1, "username": "alice", ...}

# Create a short URL
curl -X POST http://localhost:5001/urls \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://example.com", "title": "Example", "user_id": 1}'
# → {"id": 1, "short_code": "abc123", ...}

# Resolve (follow redirect)
curl -L http://localhost:5001/abc123
# → redirected to https://example.com

# Update the title
curl -X PATCH http://localhost:5001/urls/1 \
  -H "Content-Type: application/json" \
  -d '{"title": "New Title"}'

# View audit log
curl http://localhost:5001/urls/1/events
# → [{"event_type": "created", ...}, {"event_type": "updated", ...}]

# Soft delete
curl -X DELETE http://localhost:5001/urls/1
# → {"message": "deleted"}

# Confirm redirect now 404s
curl http://localhost:5001/abc123
# → {"error": "not found"}
```
