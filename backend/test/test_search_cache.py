"""Tests for search cache: get_cached, set_cached, clear_cache, cache_stats."""

import time
import threading
import pytest
from agent.search_cache import (
    get_cached, set_cached, clear_cache, cache_stats,
    _fallback_cache, _fallback_lock,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Ensure cache is clean before and after each test."""
    clear_cache()
    yield
    clear_cache()


class TestCacheMiss:
    def test_get_cached_miss_returns_none(self):
        result = get_cached("nonexistent query", count=10)
        assert result is None

    def test_get_cached_miss_on_different_count(self):
        set_cached("test query", count=5, result=[{"title": "ok"}])
        result = get_cached("test query", count=10)  # different count
        assert result is None

    def test_get_cached_miss_on_different_prompt(self):
        set_cached("prompt A", count=10, result=[{"title": "ok"}])
        result = get_cached("prompt B", count=10)
        assert result is None


class TestCacheHit:
    def test_set_and_get(self):
        data = [{"title": "Result 1", "snippet": "S1"}, {"title": "Result 2", "snippet": "S2"}]
        set_cached("AI芯片市场", count=10, result=data)
        result = get_cached("AI芯片市场", count=10)
        assert result is not None
        assert len(result) == 2
        assert result[0]["title"] == "Result 1"

    def test_prompt_whitespace_normalized(self):
        """prompt IS stripped before hashing, so whitespace padding doesn't matter."""
        data = [{"title": "ok"}]
        set_cached("  padded  ", count=10, result=data)
        # Same key after strip()
        result = get_cached("padded", count=10)
        assert result is not None
        assert result[0]["title"] == "ok"


class TestCacheExpiry:
    def test_expired_entry_returns_none(self, monkeypatch):
        from agent import search_cache

        # Force memory backend by making Redis unavailable
        monkeypatch.setattr(search_cache, "_redis_available", False)
        search_cache._redis_client = None
        data = [{"title": "expired"}]
        set_cached("expiring query", count=10, result=data)

        # Simulate TTL passage by manipulating the stored timestamp
        with _fallback_lock:
            for key, (ts, val) in list(_fallback_cache.items()):
                _fallback_cache[key] = (ts - 4000, val)  # 4000s ago > 3600s TTL

        result = get_cached("expiring query", count=10)
        assert result is None


class TestClearCache:
    def test_clear_removes_all_entries(self):
        set_cached("q1", count=10, result=[{"title": "1"}])
        set_cached("q2", count=10, result=[{"title": "2"}])
        clear_cache()
        assert get_cached("q1", count=10) is None
        assert get_cached("q2", count=10) is None


class TestCacheStats:
    def test_empty_cache_stats(self, monkeypatch):
        from agent import search_cache
        monkeypatch.setattr(search_cache, "_redis_available", False)
        search_cache._redis_client = None

        clear_cache()
        stats = cache_stats()
        assert stats["total_entries"] == 0

    def test_non_empty_cache_stats(self, monkeypatch):
        from agent import search_cache
        monkeypatch.setattr(search_cache, "_redis_available", False)
        search_cache._redis_client = None

        set_cached("q1", count=10, result=[{"title": "1"}, {"title": "2"}])
        set_cached("q2", count=10, result=[{"title": "3"}])
        stats = cache_stats()
        assert stats["total_entries"] == 2
        assert stats["avg_results"] == 1.5

    def test_stats_after_expiry(self, monkeypatch):
        from agent import search_cache
        monkeypatch.setattr(search_cache, "_redis_available", False)
        search_cache._redis_client = None

        set_cached("q1", count=10, result=[{"title": "1"}])
        # Manipulate timestamp to simulate expiry
        with _fallback_lock:
            for key in list(_fallback_cache.keys()):
                ts, val = _fallback_cache[key]
                _fallback_cache[key] = (ts - 4000, val)
        stats = cache_stats()
        # Expired entries still counted in stats (they're still in dict)
        assert stats["total_entries"] == 1


class TestCacheThreadSafety:
    def test_concurrent_set(self):
        """Multiple threads writing to cache should not corrupt data."""
        errors = []

        def write_cache(i):
            try:
                data = [{"title": f"thread_{i}_result_{j}"} for j in range(5)]
                set_cached(f"thread_query_{i}", count=10, result=data)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_cache, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Verify all writes succeeded
        for i in range(10):
            result = get_cached(f"thread_query_{i}", count=10)
            assert result is not None
            assert len(result) == 5
