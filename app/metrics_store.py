"""
Thread-safe sliding-window request counter used by the alert manager.
"""
from collections import deque
from threading import Lock
import time
import statistics
import math


class MetricsStore:
    def __init__(self, window_seconds: int = 120):
        self._lock = Lock()
        self._requests: deque[float] = deque()  # request timestamps
        self._errors: deque[float] = deque()    # 5xx timestamps
        self._latencies: deque[tuple[float, float]] = deque()  # (timestamp, latency_ms)
        self._window = window_seconds

    def record(self, status_code: int, latency_ms: float | None = None) -> None:
        now = time.time()
        with self._lock:
            self._requests.append(now)
            if status_code >= 500:
                self._errors.append(now)
            if latency_ms is not None:
                try:
                    self._latencies.append((now, float(latency_ms)))
                except Exception:
                    pass
            self._evict(now)

    def _evict(self, now: float) -> None:
        cutoff = now - self._window
        while self._requests and self._requests[0] < cutoff:
            self._requests.popleft()
        while self._errors and self._errors[0] < cutoff:
            self._errors.popleft()
        while self._latencies and self._latencies[0][0] < cutoff:
            self._latencies.popleft()

    def snapshot(self) -> dict:
        now = time.time()
        with self._lock:
            self._evict(now)
            total = len(self._requests)
            errors = len(self._errors)
            lat_values = [lat for (_, lat) in self._latencies]
        rate = errors / total if total else 0.0
        latency_avg = round(statistics.mean(lat_values), 2) if lat_values else 0.0
        latency_p95 = 0.0
        if lat_values:
            sl = sorted(lat_values)
            idx = max(0, math.ceil(0.95 * len(sl)) - 1)
            latency_p95 = round(sl[idx], 2)
        return {
            "total": total,
            "errors": errors,
            "error_rate": round(rate, 4),
            "window_seconds": self._window,
            "latency_count": len(lat_values),
            "latency_avg_ms": latency_avg,
            "latency_p95_ms": latency_p95,
        }


# Global singleton — imported by create_app and AlertManager
store = MetricsStore(window_seconds=120)
