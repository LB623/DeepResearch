"""Recoverable provider for the process-local Milvus FactStore."""

from __future__ import annotations

import math
import os
import threading
import time
from collections.abc import Callable

from loguru import logger

from agent.kb.fact_store import FactStore


class FactStoreProvider:
    """Cache a FactStore and retry initialization after a bounded cooldown."""

    def __init__(
        self,
        *,
        factory: Callable[[], FactStore] = FactStore,
        retry_interval_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._factory = factory
        raw_interval = (
            retry_interval_seconds
            if retry_interval_seconds is not None
            else os.getenv("KB_RECONNECT_INTERVAL_SECONDS", "30")
        )
        try:
            parsed_interval = float(raw_interval)
        except (TypeError, ValueError):
            parsed_interval = 30.0
        if not math.isfinite(parsed_interval) or parsed_interval <= 0:
            parsed_interval = 30.0
        self._retry_interval_seconds = parsed_interval
        self._clock = clock
        self._store: FactStore | None = None
        self._next_retry_at = 0.0
        self._lock = threading.Lock()

    def get(self) -> FactStore | None:
        """Return the store, retrying a failed initialization after cooldown."""
        if self._store is not None:
            return self._store

        now = self._clock()
        if now < self._next_retry_at:
            return None

        with self._lock:
            if self._store is not None:
                return self._store
            now = self._clock()
            if now < self._next_retry_at:
                return None

            try:
                self._store = self._factory()
            except Exception as exc:
                self._next_retry_at = now + self._retry_interval_seconds
                logger.warning(
                    "[KB] FactStore unavailable error_type={} retry_in_seconds={}",
                    type(exc).__name__,
                    self._retry_interval_seconds,
                )
                return None

            self._next_retry_at = 0.0
            logger.info("[KB] FactStore connected to Milvus")
            return self._store
