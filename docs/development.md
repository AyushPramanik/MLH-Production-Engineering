# Development Guide

This file documents how to run, test, and extend the project.

## Run locally

1. Create virtualenv and install dependencies (see `README.md`).
2. Start the app for development:

```bash
python run.py
```

Set `FLASK_DEBUG=true` to enable Flask debug mode (note: when debug is enabled, Flask may re-raise exceptions and skip the app's 500 handler; use `POST /trigger-alert-now` to test alert notifications while debugging).

## Tests

Run unit tests with `pytest`:

```bash
pytest
```

## Adding or modifying alerts

- Alerts live in `app/alerting.py`.
- To add a new alert condition:
  1. Add a new `AlertState` entry in the manager's `_states` map.
 2. Implement a `_check_<name>()` method that inspects `self._metrics.snapshot()` or other signals.
 3. Call `self._notify(subject, body)` when firing; use `logger` for structured context.

## Implementing latency (p95)

Current `app/metrics_store.py` provides sliding-window counts (total / errors). To add latency and p95:

1. Store sampled durations alongside timestamps in the window (e.g. a second deque for durations).
2. On `snapshot()` compute `avg_ms`, `p95_ms` using the stored samples.
3. Keep memory bounded: consider reservoir sampling or bucketing by millisecond ranges for long windows.

## Adding a notifier

- Create a class with a `configured` property and a `send(subject, body)` method.
- Add the notifier instance to the `AlertManager` instantiation in `app/__init__.py`.

## Code style and linting

Use the repository's existing style (simple, well-structured modules). Add tests for behavior changes.
