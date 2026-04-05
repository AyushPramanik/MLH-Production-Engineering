"""
Unit tests for app/cache.py — Redis client patched at the _client level.
Tests focus on observable behavior: correct return values and silent failure on errors.
"""
import json
from unittest.mock import MagicMock, patch

import app.cache as cache_module
from app.cache import get_cache, set_cache, delete_cache, delete_cache_pattern


def test_get_cache_returns_none_on_miss():
    r = MagicMock()
    r.get.return_value = None
    with patch.object(cache_module, "_client", r):
        result = get_cache("missing_key")
    assert result is None


def test_get_cache_returns_parsed_value():
    r = MagicMock()
    r.get.return_value = json.dumps({"id": 1, "name": "alice"})
    with patch.object(cache_module, "_client", r):
        result = get_cache("users:1")
    assert result == {"id": 1, "name": "alice"}


def test_get_cache_returns_none_on_redis_exception():
    r = MagicMock()
    r.get.side_effect = Exception("connection error")
    with patch.object(cache_module, "_client", r):
        result = get_cache("some_key")
    assert result is None


def test_set_cache_does_not_raise_on_exception():
    r = MagicMock()
    r.setex.side_effect = Exception("timeout")
    with patch.object(cache_module, "_client", r):
        set_cache("key", "value")  # must not raise


def test_delete_cache_does_not_raise_on_exception():
    r = MagicMock()
    r.delete.side_effect = Exception("timeout")
    with patch.object(cache_module, "_client", r):
        delete_cache("key")  # must not raise


def test_delete_cache_pattern_does_not_raise_on_exception():
    r = MagicMock()
    r.scan.side_effect = Exception("timeout")
    with patch.object(cache_module, "_client", r):
        delete_cache_pattern("users:*")  # must not raise


def test_delete_cache_pattern_no_keys_skips_delete():
    r = MagicMock()
    r.scan.return_value = (0, [])
    with patch.object(cache_module, "_client", r):
        delete_cache_pattern("nonexistent:*")
    # When no keys are found, delete should not be called
    r.delete.assert_not_called()
