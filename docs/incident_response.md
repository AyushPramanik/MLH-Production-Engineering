# Incident Response — Mapping App Alerts

IMPORTANT: You previously asked me to check "PHE" guidance. I do not have a link or exact document yet — please paste the PHE URL or exact doc name and I will align these steps precisely with it. Below is a professional, actionable mapping of this application's alert types to an incident-response workflow suitable for public-health or operational teams.

## Scope

This document maps app-generated alerts to incident classification, immediate actions, and follow-up activities. It is intentionally concise so on-call engineers can act quickly.

## Alerts (summary)

- `service_down` — Database unreachable
- `high_error_rate` — Error rate exceeds configured threshold
- `unhandled_exception` — 500-level unhandled exceptions captured and notified
- `discord_delivery_failure` — Notifier delivery errors (403/404/DNS)

For each alert type below: Detection → Severity → Immediate Actions → Evidence → Mitigation → Post-incident.

### 1) Service Down (database unreachable)

- Detection: `service_down` alert from `AlertManager` (fired after DB check failure).
- Severity: High (application functionality limited or unavailable).
- Immediate actions:
  1. Acknowledge the alert in your incident tracker or chat channel.
 2. Check `GET /alert-status` and `GET /metrics` for current state.
 3. Tail logs: `tail -n 200 logs/app.log` for `db_check_failed` / `alert_fired` entries.
 4. Attempt a direct DB connection from host: `psql -h $DATABASE_HOST -U $DATABASE_USER -d $DATABASE_NAME` (or use `pg_isready`).
- Evidence:
  - `db_check_failed` lines in `logs/app.log` with the error string
  - `alert_fired` log entries for `service_down`
- Mitigation:
  - If DB is down: restore DB service (start container, RDS instance, or failover to replica).
  - If connectivity issue: check network ACLs, VPC routing, and DNS.
- Post-incident:
  - Run RCA: timeline, root cause, fix, and preventative actions.
  - Update `docs/operations.md` with any new steps discovered.

### 2) High Error Rate

- Detection: `high_error_rate` triggered when error-rate > `ALERT_ERROR_RATE_THRESHOLD` and requests >= `ALERT_MIN_REQUESTS`.
- Severity: Medium → High depending on impact (user-facing errors, partial failures).
- Immediate actions:
  1. Check `GET /metrics` for error counts and rate.
 2. Inspect recent logs: `GET /logs` endpoint or `tail -n 500 logs/app.log`.
 3. Identify trending stack traces or root exceptions. Search `logs/app.log` for repeated `error` messages.
- Evidence:
  - `alert_fired` log entries for `high_error_rate` with attached snapshot of metrics
  - Recent stack traces in logs
- Mitigation:
  - Roll back recent deployments if correlating with spike.
  - Apply hotfix (config or code) or scale resources if saturation-related.
  - If a specific endpoint is failing, temporarily disable or rate-limit it.
- Post-incident:
  - Create a postmortem with scope, impact, timeline, RCA, and preventive measures.

### 3) Unhandled Exceptions / Runtime Errors

- Detection: 500 handler records exception and triggers `_notify` for immediate alert.
- Severity: Varies (investigate frequency and affected endpoints).
- Immediate actions:
  1. Collect the full traceback from `logs/app.log`.
 2. Reproduce locally if possible and add a failing test.
 3. Apply and deploy a fix; validate via automated tests.

### 4) Notifier failures (Discord / Email)

- Detection: `discord_alert_failed` or `alert_email_failed` log entries.
- Common causes: invalid webhook (404/10015), revoked webhook token, DNS/network issues, SMTP auth failure.
- Immediate actions:
  1. Inspect the log entry for `discord_alert_failed` — it may include HTTP status and response body.
 2. Validate `DISCORD_WEBHOOK_URL` (do not paste secrets into chat) and test with a direct `curl` POST.

```bash
curl -H "Content-Type: application/json" -d '{"content":"test"}' "$DISCORD_WEBHOOK_URL"
```

3. For 403/404/10015: create a new webhook in Discord and update `DISCORD_WEBHOOK_URL`.

---

## Communication and Escalation

- Use your standard incident channel (Slack/MS Teams) and tag on-call.
- Triage severity and escalate according to organisational policy (PHE-specific escalation should be inserted once the PHE reference document is provided).

## Post-incident

- Prepare a postmortem (summary, timeline, impact, root cause, fix, follow-ups).
- If PHE guidance applies, include required public-health reporting fields (contact, time, impact) — I will add those if you provide the exact PHE doc.
