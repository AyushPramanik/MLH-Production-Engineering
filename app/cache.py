import json
import os
import threading
import time
from typing import Any

import redis

_DEFAULT_TTL = 60  # seconds

# Circuit-breaker: after a Redis failure, skip all Redis calls for this many
# seconds before trying again.  This prevents per-request 0.2 s connection
# timeouts from stacking up when Redis is unavailable.
_CIRCUIT_OPEN_DURATION = 30  # seconds

_client: redis.Redis | None = None
_circuit_open_until: float = 0.0  # monotonic timestamp; 0 means closed
_circuit_lock = threading.Lock()


def _circuit_is_open() -> bool:
    with _circuit_lock:
        return time.monotonic() < _circuit_open_until


def _trip_circuit() -> None:
    with _circuit_lock:
        global _circuit_open_until
        _circuit_open_until = time.monotonic() + _CIRCUIT_OPEN_DURATION


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis(
            host=os.environ.get("REDIS_HOST", "localhost"),
            port=int(os.environ.get("REDIS_PORT", 6379)),
            decode_responses=True,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )
    return _client


def get_cache(key: str):
    if _circuit_is_open():
        return None
    try:
        value = get_redis().get(key)
        if value is None:
            return None
        return json.loads(value)
    except Exception:
        _trip_circuit()
        return None


def set_cache(key: str, value: Any, ttl: int = _DEFAULT_TTL) -> None:
    if _circuit_is_open():
        return
    try:
        get_redis().setex(key, ttl, json.dumps(value))
    except Exception:
        _trip_circuit()


def delete_cache(key: str) -> None:
    if _circuit_is_open():
        return
    try:
        get_redis().delete(key)
    except Exception:
        _trip_circuit()


def delete_cache_pattern(pattern: str) -> None:
    if _circuit_is_open():
        return
    try:
        r = get_redis()
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match=pattern, count=100)
            if keys:
                r.delete(*keys)
            if cursor == 0:
                break
    except Exception:
        _trip_circuit()
