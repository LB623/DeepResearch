"""Tests for RateLimiter — token bucket rate limiter with thread safety."""

import time
import threading
import pytest
from agent.base_agent import RateLimiter, get_web_search_rate_limiter


class TestRateLimiterInit:
    def test_default_qps(self):
        rl = RateLimiter(max_qps=15.0)
        assert rl.max_qps == 15.0
        assert rl.min_interval == 1.0 / 15.0

    def test_custom_qps(self):
        rl = RateLimiter(max_qps=100.0)
        assert rl.max_qps == 100.0
        assert rl.min_interval == 0.01


class TestRateLimiterAcquire:
    def test_first_acquire_no_wait(self):
        rl = RateLimiter(max_qps=100.0)
        wait_time = rl.acquire()
        assert wait_time == 0.0

    def test_rapid_acquires_get_throttled(self, monkeypatch):
        """Verify that rapid acquires within the interval trigger waits."""
        rl = RateLimiter(max_qps=2.0)  # min_interval = 0.5s
        # First acquire — no wait
        assert rl.acquire() == 0.0
        # Second acquire within 0.5s — should wait
        wait_time = rl.acquire()
        assert wait_time > 0.0

    def test_acquire_after_interval_no_wait(self, monkeypatch):
        rl = RateLimiter(max_qps=2.0)  # min_interval = 0.5s
        rl.acquire()
        # Simulate time passing
        rl.last_request_time = time.time() - 1.0  # 1 second ago
        assert rl.acquire() == 0.0


class TestRateLimiterThreadSafety:
    def test_concurrent_acquires(self):
        """Multiple threads acquiring simultaneously should not deadlock or corrupt state."""
        rl = RateLimiter(max_qps=1000.0)  # very high QPS, minimal waiting
        results = []
        errors = []

        def acquire():
            try:
                wt = rl.acquire()
                results.append(wt)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=acquire) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 20


class TestGetWebSearchRateLimiter:
    def test_singleton_behavior(self, monkeypatch):
        monkeypatch.setenv("WEB_SEARCH_MAX_QPS", "50")
        # Reset singleton for test
        import agent.base_agent as ba
        ba._web_search_rate_limiter = None

        rl1 = get_web_search_rate_limiter()
        rl2 = get_web_search_rate_limiter()
        assert rl1 is rl2
        assert rl1.max_qps == 50.0

    def test_respects_env_var(self, monkeypatch):
        monkeypatch.setenv("WEB_SEARCH_MAX_QPS", "25")
        import agent.base_agent as ba
        ba._web_search_rate_limiter = None

        rl = get_web_search_rate_limiter()
        assert rl.max_qps == 25.0
