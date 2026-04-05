"""
Unit tests for MetricsStore — the thread-safe sliding-window counter.
No mocking needed; this is pure Python with no external dependencies.
"""
import time

from app.metrics_store import MetricsStore


def test_snapshot_empty():
    store = MetricsStore(window_seconds=60)
    snap = store.snapshot()
    assert snap["total"] == 0
    assert snap["errors"] == 0
    assert snap["error_rate"] == 0.0
    assert snap["window_seconds"] == 60


def test_record_200_increments_total():
    store = MetricsStore(window_seconds=60)
    store.record(200)
    store.record(201)
    snap = store.snapshot()
    assert snap["total"] == 2
    assert snap["errors"] == 0
    assert snap["error_rate"] == 0.0


def test_record_500_increments_errors():
    store = MetricsStore(window_seconds=60)
    store.record(200)
    store.record(500)
    store.record(503)
    snap = store.snapshot()
    assert snap["total"] == 3
    assert snap["errors"] == 2
    assert round(snap["error_rate"], 4) == round(2 / 3, 4)


def test_eviction_removes_old_entries():
    store = MetricsStore(window_seconds=1)
    store.record(200)
    store.record(500)
    time.sleep(1.1)
    # After window expires, old entries should be evicted on next snapshot
    snap = store.snapshot()
    assert snap["total"] == 0
    assert snap["errors"] == 0


def test_only_5xx_counted_as_errors():
    store = MetricsStore(window_seconds=60)
    for code in [200, 201, 301, 400, 404, 422]:
        store.record(code)
    snap = store.snapshot()
    assert snap["errors"] == 0
    assert snap["total"] == 6


def test_error_rate_all_errors():
    store = MetricsStore(window_seconds=60)
    store.record(500)
    store.record(500)
    snap = store.snapshot()
    assert snap["error_rate"] == 1.0
