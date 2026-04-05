# Operations Runbook

This runbook provides concise, actionable commands and checks to operate the service and recover from common problems.

## Useful endpoints

- `GET /metrics` — metrics snapshot used for alerting
- `GET /alert-status` — alert state and thresholds
- `GET /logs` — recent structured logs
- `GET /dashboard` — monitoring dashboard

## Check service status

1. Check process / container

```bash
# If running locally with Python
ps aux | grep run.py

# If using Docker Compose
docker compose ps
docker compose logs -f
```

2. Tail application logs

```bash
tail -n 500 logs/app.log
```

3. Inspect health endpoints

```bash
curl -sS http://127.0.0.1:5000/metrics | jq .
curl -sS http://127.0.0.1:5000/alert-status | jq .
```

## Verifying notifier health (Discord)

1. Check recent `discord_alert_failed` entries in `logs/app.log`.
2. Test the webhook directly (replace `$DISCORD_WEBHOOK_URL` in your environment):

```bash
curl -H "Content-Type: application/json" -d '{"content":"mlh-pde webhook test"}' "$DISCORD_WEBHOOK_URL"
```

3. Common failure modes and quick fixes:
- 403 / 404 with response `{"message":"Unknown Webhook","code":10015}`: webhook is invalid or deleted — re-create webhook in Discord and update `DISCORD_WEBHOOK_URL`.
- DNS / `getaddrinfo` failures: check host DNS and network connectivity; ensure container host has internet access.

## Verifying email notifier

1. Ensure `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_EMAIL_TO` are set.
2. Send a simple test email via the app's `EmailNotifier` test route (if present) or a small Python snippet using the same SMTP settings.

## Database checks

1. Attempt to connect from the host using `psql` or `pg_isready`:

```bash
PGPASSWORD=$DATABASE_PASSWORD psql -h $DATABASE_HOST -U $DATABASE_USER -d $DATABASE_NAME -c '\l'
```

2. If Postgres is unreachable: check container, service, firewall, or RDS health.

## Restart steps

1. Local (development): stop and restart the Python process

```bash
# Ctrl+C the running process, then
python run.py
```

2. Docker Compose

```bash
docker compose down
docker compose up -d --build
```

3. Rolling deploy / production: follow your orchestrator's procedures (Kubernetes, systemd, etc.).

## When alerts don't arrive in chat

1. Confirm `DISCORD_WEBHOOK_URL` is set in the running environment (containers, systemd unit, or process env).
2. Re-run a test `curl` to the webhook (see above).
3. Examine `logs/app.log` for `discord_alert_failed` details.
4. If `discord_alert_failed` shows HTTP 403/404: recreate webhook in Discord and update the environment variable; restart the app.

## Contact / Escalation

Follow your team's standard escalation policy. Add contact details and phone numbers here if required by PHE or organisational policy.
