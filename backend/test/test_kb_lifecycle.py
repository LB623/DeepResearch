"""Tests for KB lifecycle mode — freshness filtering, confidence decay,
and mode-switching behaviour.
"""

import os
import time
import pytest
from agent.kb.lifecycle import (
    CATEGORY_TTL,
    FRESHNESS_MAX_AGE,
    KBLifecycleMode,
    get_mode,
    should_decay,
    should_filter,
    should_tag,
    should_warn,
)


# ═══════════════════════════════════════════════════════════════════════
# Mode resolution
# ═══════════════════════════════════════════════════════════════════════

class TestGetMode:
    def test_defaults_to_freshness_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("KB_LIFECYCLE_MODE", raising=False)
        assert get_mode() == KBLifecycleMode.FRESHNESS

    def test_reads_from_env(self, monkeypatch):
        monkeypatch.setenv("KB_LIFECYCLE_MODE", "off")
        assert get_mode() == KBLifecycleMode.OFF

    def test_invalid_env_falls_back_to_freshness(self, monkeypatch):
        monkeypatch.setenv("KB_LIFECYCLE_MODE", "garbage")
        assert get_mode() == KBLifecycleMode.FRESHNESS


# ═══════════════════════════════════════════════════════════════════════
# Helper predicates
# ═══════════════════════════════════════════════════════════════════════

class TestShouldFilter:
    def test_off_false(self):
        assert not should_filter(KBLifecycleMode.OFF)

    def test_inform_false(self):
        assert not should_filter(KBLifecycleMode.INFORM)

    def test_freshness_true(self):
        assert should_filter(KBLifecycleMode.FRESHNESS)

    def test_lifecycle_true(self):
        assert should_filter(KBLifecycleMode.LIFECYCLE)


class TestShouldDecay:
    def test_off_false(self):
        assert not should_decay(KBLifecycleMode.OFF)

    def test_inform_false(self):
        assert not should_decay(KBLifecycleMode.INFORM)

    def test_freshness_true(self):
        assert should_decay(KBLifecycleMode.FRESHNESS)

    def test_lifecycle_true(self):
        assert should_decay(KBLifecycleMode.LIFECYCLE)


class TestShouldTag:
    def test_off_false(self):
        assert not should_tag(KBLifecycleMode.OFF)

    def test_inform_true(self):
        assert should_tag(KBLifecycleMode.INFORM)

    def test_freshness_true(self):
        assert should_tag(KBLifecycleMode.FRESHNESS)

    def test_lifecycle_true(self):
        assert should_tag(KBLifecycleMode.LIFECYCLE)


class TestShouldWarn:
    def test_off_false(self):
        assert not should_warn(KBLifecycleMode.OFF)

    def test_inform_true(self):
        assert should_warn(KBLifecycleMode.INFORM)

    def test_freshness_true(self):
        assert should_warn(KBLifecycleMode.FRESHNESS)

    def test_lifecycle_true(self):
        assert should_warn(KBLifecycleMode.LIFECYCLE)


# ═══════════════════════════════════════════════════════════════════════
# Threshold constants
# ═══════════════════════════════════════════════════════════════════════

class TestFreshnessMaxAge:
    def test_high_is_7_days(self):
        assert FRESHNESS_MAX_AGE["high"] == 7

    def test_medium_is_30_days(self):
        assert FRESHNESS_MAX_AGE["medium"] == 30

    def test_low_is_180_days(self):
        assert FRESHNESS_MAX_AGE["low"] == 180


class TestCategoryTTL:
    def test_market_data_7_days(self):
        assert CATEGORY_TTL["market_data"] == 7

    def test_product_info_30_days(self):
        assert CATEGORY_TTL["product_info"] == 30

    def test_strategy_90_days(self):
        assert CATEGORY_TTL["strategy"] == 90

    def test_technology_180_days(self):
        assert CATEGORY_TTL["technology"] == 180

    def test_historical_is_none(self):
        assert CATEGORY_TTL["historical"] is None


# ═══════════════════════════════════════════════════════════════════════
# FactStore query — freshness filter + decay (unit-level with mocks)
# ═══════════════════════════════════════════════════════════════════════

class TestFactStoreFreshnessFilter:
    """Test that query() with max_age_days excludes stale facts."""

    def test_filters_expired_fact(self):
        from agent.kb.fact_store import FactStore

        # Build a hit with a fake created_at that is 100 days old
        old_ts = time.time() - 100 * 86400
        mock_entity = {
            "fact_text": "old fact",
            "source_url": "https://x.com",
            "research_topic": "test",
            "confidence": 0.9,
            "created_at": old_ts,
        }
        self._patch_and_assert_filtered(
            mock_entity, max_age_days=30, expected_count=0,
            reason="100-day-old fact should be filtered when max_age=30"
        )

    def test_keeps_fresh_fact(self):
        from agent.kb.fact_store import FactStore

        recent_ts = time.time() - 5 * 86400
        mock_entity = {
            "fact_text": "recent fact",
            "source_url": "https://x.com",
            "research_topic": "test",
            "confidence": 0.9,
            "created_at": recent_ts,
        }
        self._patch_and_assert_filtered(
            mock_entity, max_age_days=30, expected_count=1,
            reason="5-day-old fact should pass when max_age=30"
        )

    def test_confidence_decay_over_time(self):
        from agent.kb.fact_store import FactStore

        # 25 days old — passes max_age=30 filter, but old enough for visible decay
        old_ts = time.time() - 25 * 86400
        mock_entity = {
            "fact_text": "aging fact",
            "source_url": "https://x.com",
            "research_topic": "test",
            "confidence": 0.9,
            "created_at": old_ts,
        }
        # max_age=30, decay=True → 25 days old
        # decay_factor = max(0.3, 1.0 - 25/(30*2)) = max(0.3, 1.0 - 0.417) = 0.583
        # confidence = 0.9 * 0.583 = 0.525 → round to 0.53
        # Actually: max(0.3, 1.0 - 25/60) = max(0.3, 0.583) = 0.583
        # confidence = 0.9 * 0.583 = 0.525 → round(0.525, 2) = 0.53
        expected_confidence = round(0.9 * max(0.3, 1.0 - 25 / 60), 2)
        self._patch_and_assert_decay(
            mock_entity, max_age_days=30, decay=True,
            expected_confidence=expected_confidence,
            reason="25-day-old fact with max_age=30 should have decayed confidence"
        )

    def _patch_and_assert_filtered(self, entity, max_age_days, expected_count, reason=""):
        from agent.kb.fact_store import FactStore
        from unittest.mock import MagicMock, patch

        with patch("agent.kb.fact_store.MilvusClient") as mc, \
             patch("agent.kb.fact_store.requests.post") as mp:
            mc_client = MagicMock()
            mc_client.has_collection.return_value = True
            mc_client.search.return_value = [[
                {"entity": entity, "distance": 0.05}
            ]]
            mc.return_value = mc_client

            mr = MagicMock()
            mr.raise_for_status.return_value = None
            mr.json.return_value = {
                "data": [{"embedding": [0.1] * 1024, "index": 0}]
            }
            mp.return_value = mr

            store = FactStore()
            results = store.query("test", max_age_days=max_age_days)
            assert len(results) == expected_count, reason

    def _patch_and_assert_decay(self, entity, max_age_days, decay, expected_confidence, reason=""):
        from agent.kb.fact_store import FactStore
        from unittest.mock import MagicMock, patch

        with patch("agent.kb.fact_store.MilvusClient") as mc, \
             patch("agent.kb.fact_store.requests.post") as mp:
            mc_client = MagicMock()
            mc_client.has_collection.return_value = True
            mc_client.search.return_value = [[
                {"entity": entity, "distance": 0.05}
            ]]
            mc.return_value = mc_client

            mr = MagicMock()
            mr.raise_for_status.return_value = None
            mr.json.return_value = {
                "data": [{"embedding": [0.1] * 1024, "index": 0}]
            }
            mp.return_value = mr

            store = FactStore()
            results = store.query("test", max_age_days=max_age_days, decay=decay)
            assert len(results) == 1, reason
            assert results[0]["confidence"] == expected_confidence, (
                f"{reason}: got {results[0]['confidence']}, expected {expected_confidence}"
            )


class TestFactStoreLifecycleFilter:
    """Test per-category TTL filtering in lifecycle mode."""

    def test_market_data_expires_after_7_days(self):
        old_ts = time.time() - 10 * 86400  # 10 days old
        entity = {
            "fact_text": "old market data",
            "source_url": "https://x.com",
            "research_topic": "test",
            "confidence": 0.9,
            "created_at": old_ts,
            "fact_category": "market_data",
        }
        self._patch_and_assert_count(
            entity, lifecycle_mode=True, expected_count=0,
            reason="10-day-old market_data should be filtered (TTL=7)"
        )

    def test_historical_never_expires(self):
        old_ts = time.time() - 400 * 86400  # 400 days old
        entity = {
            "fact_text": "old historical fact",
            "source_url": "https://x.com",
            "research_topic": "test",
            "confidence": 0.9,
            "created_at": old_ts,
            "fact_category": "historical",
        }
        self._patch_and_assert_count(
            entity, lifecycle_mode=True, expected_count=1,
            reason="historical facts should never be filtered (TTL=None)"
        )

    def test_technology_kept_within_180_days(self):
        recent_ts = time.time() - 150 * 86400
        entity = {
            "fact_text": "tech fact",
            "source_url": "https://x.com",
            "research_topic": "test",
            "confidence": 0.9,
            "created_at": recent_ts,
            "fact_category": "technology",
        }
        self._patch_and_assert_count(
            entity, lifecycle_mode=True, expected_count=1,
            reason="150-day-old technology fact should pass (TTL=180)"
        )

    def _patch_and_assert_count(self, entity, lifecycle_mode, expected_count, reason=""):
        from agent.kb.fact_store import FactStore
        from unittest.mock import MagicMock, patch

        with patch("agent.kb.fact_store.MilvusClient") as mc, \
             patch("agent.kb.fact_store.requests.post") as mp:
            mc_client = MagicMock()
            mc_client.has_collection.return_value = True
            mc_client.search.return_value = [[
                {"entity": entity, "distance": 0.05}
            ]]
            mc.return_value = mc_client

            mr = MagicMock()
            mr.raise_for_status.return_value = None
            mr.json.return_value = {
                "data": [{"embedding": [0.1] * 1024, "index": 0}]
            }
            mp.return_value = mr

            store = FactStore()
            results = store.query("test", lifecycle_mode=lifecycle_mode)
            assert len(results) == expected_count, reason


# ═══════════════════════════════════════════════════════════════════════
# FactStore add_facts — fact_category storage
# ═══════════════════════════════════════════════════════════════════════

class TestFactStoreAddFactsCategory:
    def test_fact_category_stored(self):
        """Verify fact_category is passed through to Milvus insert."""
        from agent.kb.fact_store import FactStore
        from unittest.mock import MagicMock, patch

        with patch("agent.kb.fact_store.MilvusClient") as mc, \
             patch("agent.kb.fact_store.requests.post") as mp:
            mc_client = MagicMock()
            mc_client.has_collection.return_value = True
            mc_client.insert.return_value = {"insert_count": 1}
            mc.return_value = mc_client

            mr = MagicMock()
            mr.raise_for_status.return_value = None
            mr.json.return_value = {
                "data": [{"embedding": [0.1] * 1024, "index": 0}]
            }
            mp.return_value = mr

            store = FactStore()
            store.add_facts([{
                "fact": "market data fact",
                "source_url": "https://x.com",
                "confidence": 0.95,
                "fact_category": "market_data",
            }])

            insert_arg = mc_client.insert.call_args[1]["data"][0]
            assert insert_arg["fact_category"] == "market_data"
            assert insert_arg["fact_text"] == "market data fact"
