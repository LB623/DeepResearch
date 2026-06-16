"""搜索缓存 — Redis 后端，多实例共享，TTL 自动过期。

缓存 MCP 网页搜索结果，以 (prompt, count) 为 key，避免跨线程和跨实例的
重复 API 调用。Redis 不可用时自动降级为进程内内存缓存。

Usage:
    from agent.search_cache import get_cached, set_cached

    cached = get_cached("AI芯片市场趋势", count=10)
    if cached is not None:
        return cached
    result = do_expensive_search(...)
    set_cached("AI芯片市场趋势", count=10, result=result)
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from typing import Optional

import redis
from loguru import logger

# ── configuration ─────────────────────────────────────────────────────
DEFAULT_TTL = 3600  # 秒（1 小时）
TRUNCATE_LEN = 80   # 日志中截断 query / title 时的最大字符数
REDIS_KEY_PREFIX = "search_cache"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ── Redis 连接（惰性初始化）───────────────────────────────────────────
_redis_client: redis.Redis | None = None
_redis_available: bool | None = None  # None=未检测, True=可用, False=不可用

# ── 降级：内存缓存（Redis 不可用时使用）────────────────────────────────
_fallback_cache: dict[str, tuple[float, list[dict]]] = {}
_fallback_lock = threading.Lock()


def _get_redis() -> redis.Redis | None:
    """获取 Redis 连接。不可用时返回 None。"""
    global _redis_client, _redis_available
    if _redis_available is False:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        _redis_client.ping()
        _redis_available = True
        logger.info("[Cache] Redis 连接成功，缓存跨实例共享")
        return _redis_client
    except Exception as exc:
        _redis_available = False
        _redis_client = None
        logger.warning(f"[Cache] Redis 不可用 ({type(exc).__name__}: {exc})，降级为进程内缓存")
        return None


def _make_key(prompt: str, count: int) -> str:
    """生成确定性的缓存 key。"""
    payload = f"{prompt.strip()}:{count}"
    return f"{REDIS_KEY_PREFIX}:{hashlib.md5(payload.encode('utf-8')).hexdigest()}"


def get_cached(prompt: str, count: int = 10) -> Optional[list[dict]]:
    """返回缓存的搜索结果（如果存在且未过期），否则返回 None。

    命中时打印前 3 条结果的标题，未命中时打印简要日志。
    """
    key = _make_key(prompt, count)
    r = _get_redis()

    if r is not None:
        # ── Redis 路径 ────────────────────────────────────────────
        try:
            raw = r.get(key)
            if raw is None:
                logger.info(f"[Cache] ✗ MISS — '{prompt[:TRUNCATE_LEN]}' 未命中，将通过MCP搜索")
                return None
            result = json.loads(raw)
            remaining_ttl = r.ttl(key)
            titles = [
                r.get("title", r.get("snippet", "?"))[:TRUNCATE_LEN]
                for r in result[:3]
            ]
            logger.info(
                f"[Cache] ✓ HIT — '{prompt[:TRUNCATE_LEN]}' 命中缓存 "
                f"（{len(result)} 条结果, 剩余TTL={remaining_ttl}s）"
            )
            logger.info(f"[Cache]   Top results: {', '.join(titles)}")
            return result
        except Exception as exc:
            logger.warning(f"[Cache] Redis 读取失败 ({type(exc).__name__}): {exc}")
            return None

    # ── 降级：内存缓存路径 ─────────────────────────────────────────
    with _fallback_lock:
        if key not in _fallback_cache:
            logger.info(f"[Cache] ✗ MISS — '{prompt[:TRUNCATE_LEN]}' 未命中，将通过MCP搜索")
            return None

        ts, result = _fallback_cache[key]
        remaining = DEFAULT_TTL - (time.time() - ts)

        if remaining <= 0:
            logger.info(
                f"[Cache] ✗ EXPIRED — '{prompt[:TRUNCATE_LEN]}' 缓存已过期（TTL={DEFAULT_TTL}s），将重新搜索"
            )
            del _fallback_cache[key]
            return None

    titles = [
        r.get("title", r.get("snippet", "?"))[:TRUNCATE_LEN]
        for r in result[:3]
    ]
    logger.info(
        f"[Cache] ✓ HIT — '{prompt[:TRUNCATE_LEN]}' 命中缓存 "
        f"（{len(result)} 条结果, 剩余TTL={remaining:.0f}s）"
    )
    logger.info(f"[Cache]   Top results: {', '.join(titles)}")
    return result


def set_cached(prompt: str, count: int, result: list[dict]) -> None:
    """将搜索结果存入缓存。"""
    key = _make_key(prompt, count)
    r = _get_redis()

    if r is not None:
        # ── Redis 路径：SETEX 自带 TTL ────────────────────────────
        try:
            r.setex(key, DEFAULT_TTL, json.dumps(result, ensure_ascii=False))
            logger.info(
                f"[Cache] stored — '{prompt[:TRUNCATE_LEN]}' "
                f"（{len(result)} items, TTL={DEFAULT_TTL}s）→ Redis"
            )
        except Exception as exc:
            logger.warning(f"[Cache] Redis 写入失败 ({type(exc).__name__}): {exc}")
        return

    # ── 降级：内存缓存路径 ─────────────────────────────────────────
    with _fallback_lock:
        _fallback_cache[key] = (time.time(), result)
    logger.info(
        f"[Cache] stored — '{prompt[:TRUNCATE_LEN]}' "
        f"（{len(result)} items, TTL={DEFAULT_TTL}s）→ 内存"
    )


def clear_cache() -> None:
    """清空所有缓存条目（用于测试）。"""
    r = _get_redis()
    if r is not None:
        try:
            # SCAN 遍历所有 search_cache 前缀的 key 并删除
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = r.scan(cursor, match=f"{REDIS_KEY_PREFIX}:*", count=100)
                if keys:
                    deleted += r.delete(*keys)
                if cursor == 0:
                    break
            logger.info(f"[Cache] cleared all {deleted} entries (Redis)")
        except Exception as exc:
            logger.warning(f"[Cache] Redis 清空失败 ({type(exc).__name__}): {exc}")
        return

    with _fallback_lock:
        count = len(_fallback_cache)
        _fallback_cache.clear()
    logger.info(f"[Cache] cleared all {count} entries (内存)")


def cache_stats() -> dict:
    """返回当前缓存统计信息（用于监控）。"""
    r = _get_redis()
    if r is not None:
        try:
            # 统计 search_cache 前缀的 key 数量
            count = 0
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor, match=f"{REDIS_KEY_PREFIX}:*", count=100)
                count += len(keys)
                if cursor == 0:
                    break
            return {
                "total_entries": count,
                "backend": "redis",
            }
        except Exception as exc:
            logger.warning(f"[Cache] Redis 统计失败 ({type(exc).__name__}): {exc}")
            return {"total_entries": "unknown", "backend": "redis"}

    now = time.time()
    with _fallback_lock:
        entries = []
        for key, (ts, res) in _fallback_cache.items():
            entries.append({
                "remaining_ttl": max(0, DEFAULT_TTL - (now - ts)),
                "result_count": len(res),
            })
    return {
        "total_entries": len(entries),
        "avg_results": sum(e["result_count"] for e in entries) / max(len(entries), 1),
        "oldest_ttl": min((e["remaining_ttl"] for e in entries), default=0),
        "backend": "memory",
    }
