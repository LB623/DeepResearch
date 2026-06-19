"""基于 Milvus 的研究知识库事实存储库。

使用 MilvusClient API（PyMilvus 2.5+）实现以下功能：
  - 集合管理（首次使用时自动创建）
  - 批量插入提取的事实及其嵌入
  - 语义搜索（向量相似度）+ 可选的元数据过滤

Usage:
    from agent.kb.fact_store import FactStore

    store = FactStore()
    store.add_facts([{
        "fact": "2025年AI编程助手市场规模达15亿美元",
        "source_url": "https://...",
        "research_topic": "AI编程助手市场分析",
        "confidence": 0.9,
    }])

    results = store.query("AI编程助手发展趋势", top_k=10)
"""

from __future__ import annotations

import json
import os
import time
import asyncio
from datetime import datetime
from typing import Any, Optional

import requests
from loguru import logger
from pymilvus import MilvusClient
from agent.exceptions import (
    KBConnectionError,
    KBEmbeddingError,
    KBEmbeddingFatalError,
    KBConfigError,
)
from pymilvus.milvus_client.index import IndexParams

# ── constants ─────────────────────────────────────────────────────────
COLLECTION_NAME = "research_facts"
DEFAULT_EMBEDDING_DIM = 1024
DEFAULT_EMBEDDING_MODEL = "text-embedding-v3"


class FactStore:
    """Milvus-backed storage and retrieval of research facts."""

    def __init__(
        self,
        uri: str | None = None,
        collection: str | None = None,
        embedding_dim: int | None = None,
        embedding_model: str | None = None,
    ):
        self.uri = uri or os.getenv("MILVUS_URI", "http://localhost:19530")
        self.collection = collection or os.getenv("MILVUS_COLLECTION", COLLECTION_NAME)
        self.embedding_dim = embedding_dim or int(
            os.getenv("EMBEDDING_DIM", str(DEFAULT_EMBEDDING_DIM))
        )
        self.embedding_model = embedding_model or os.getenv(
            "EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL
        )

        self._client: MilvusClient | None = None
        self._ensure_collection()

    # ── public API ──────────────────────────────────────────────────

    def add_facts(self, facts: list[dict]) -> int:
        """将fact嵌入并插入到 Milvus 中。返回已插入的事实数量。

        每个fact字典必须包含：
          - fact (str): 事实陈述
          - source_url (str): 事实来源
        Optional:
          - research_topic (str): 触发此搜索的研究主题
          - confidence (float): 0.0-1.0
        """
        if not facts:
            return 0

        texts = [f["fact"] for f in facts]
        embeddings = self._embed(texts)

        data = []
        now = int(time.time())
        for i, fact in enumerate(facts):
            data.append({
                "vector": embeddings[i],
                "fact_text": fact["fact"],
                "source_url": fact.get("source_url", ""),
                "research_topic": fact.get("research_topic", ""),
                "confidence": float(fact.get("confidence", 1.0)),
                "fact_category": fact.get("fact_category", "strategy"),
                "created_at": now,
            })

        result = self.client.insert(collection_name=self.collection, data=data)
        inserted = result.get("insert_count", len(data))
        logger.info(
            f"[KB] stored {inserted} facts → Milvus/{self.collection} "
            f"(topics: {set(f.get('research_topic', '') for f in facts)})"
        )
        return inserted

    def query(
        self,
        topic: str,
        top_k: int = 10,
        min_confidence: float = 0.0,
        max_age_days: int | None = None,
        decay: bool = False,
        lifecycle_mode: bool = False,
    ) -> list[dict]:
        """对与研究主题相关的fact进行语义搜索。

        Args:
            topic: 用于语义搜索的研究主题文本。
            top_k:
            min_confidence: 过滤前的最小置信度（0.0-1.0）。
            max_age_days: 排除超过指定天数的事实。None 表示无限制。
                在 lifecycle_mode 模式下，此参数将被忽略，而是使用按类别划分的 TTL（生存时间）。
            decay: 如果为 True，则应用基于时间的置信度衰减。
            lifecycle_mode: 如果为 True，则使用按类别划分的 TTL（CATEGORY_TTL），
                而不是单一的 max_age_days 阈值。

        Returns list of {fact, source_url, confidence, research_topic, relevance,
                          created_at, age_days, fact_category}.
        """
        from agent.kb.lifecycle import CATEGORY_TTL

        embedding = self._embed([topic])
        results = self.client.search(
            collection_name=self.collection,
            data=[embedding[0]],
            limit=top_k,
            output_fields=[
                "fact_text", "source_url", "research_topic",
                "confidence", "created_at", "fact_category",
            ],
        )

        if not results or not results[0]:
            logger.info(f"[KB] query '{topic[:60]}...' → 0 results")
            return []

        now = time.time()
        hits = []
        for hit in results[0]:
            entity = hit.get("entity", {})
            score = 1.0 - hit.get("distance", 0)  # 余弦距离 → 相似度

            # ── confidence floor check ──
            raw_confidence = entity.get("confidence", 1.0)
            if raw_confidence < min_confidence:
                continue

            # ── age calculation ──
            created = entity.get("created_at", 0)
            age_days = (now - created) / 86400 if created else 36500

            # ── freshness filter ──
            if lifecycle_mode:
                category = entity.get("fact_category", "strategy")
                category_max_age = CATEGORY_TTL.get(category)
                if category_max_age is not None and age_days > category_max_age:
                    continue
            elif max_age_days and age_days > max_age_days:
                continue

            # ── confidence decay ──
            confidence = raw_confidence
            if decay:
                effective_max_age = max_age_days or 30
                if lifecycle_mode:
                    category = entity.get("fact_category", "strategy")
                    effective_max_age = CATEGORY_TTL.get(category)
                    if effective_max_age is None:
                        effective_max_age = 180  # no-decay fallback for None TTL
                decay_factor = max(0.3, 1.0 - age_days / (effective_max_age * 2))
                confidence = raw_confidence * decay_factor

            hits.append({
                "fact": entity.get("fact_text", ""),
                "source_url": entity.get("source_url", ""),
                "research_topic": entity.get("research_topic", ""),
                "confidence": round(confidence, 2),
                "relevance": round(score, 3),
                "created_at": created,
                "age_days": round(age_days, 1),
                "fact_category": entity.get("fact_category", "strategy"),
            })

        logger.info(
            f"[KB] query '{topic[:60]}...' → {len(hits)} hits "
            f"(top score={hits[0]['relevance']:.3f})"
            if hits else f"[KB] query '{topic[:60]}...' → 0 hits"
        )
        return hits

    def stats(self) -> dict:
        """Return collection statistics."""
        try:
            stat = self.client.get_collection_stats(self.collection)
            return {
                "collection": self.collection,
                "row_count": stat.get("row_count", 0),
            }
        except ConnectionError as e:
            logger.warning(f"[KB] failed to get collection stats (connection): {e}")
            return {"collection": self.collection, "row_count": "unknown"}
        except Exception as e:
            logger.warning(f"[KB] failed to get collection stats ({type(e).__name__}): {e}")
            return {"collection": self.collection, "row_count": "unknown"}

    # ── internal helpers ────────────────────────────────────────────

    @property
    def client(self) -> MilvusClient:
        if self._client is None:
            self._client = MilvusClient(uri=self.uri)
        return self._client

    def _ensure_collection(self) -> None:
        """Create the collection if it doesn't exist."""
        if self.client.has_collection(self.collection):
            logger.info(f"[KB] collection '{self.collection}' already exists")
            return

        self.client.create_collection(
            collection_name=self.collection,
            dimension=self.embedding_dim,
            metric_type="COSINE",
            auto_id=True,
            enable_dynamic_field=True,
        )
        # 创建 IVF_FLAT 索引以提高搜索效率。
        # Note: 某些 Milvus 版本会自动创建默认索引。
        try:
            index_params = IndexParams()
            index_params.add_index(
                field_name="vector",
                index_type="IVF_FLAT",
                metric_type="COSINE",
                params={"nlist": 128},
            )
            self.client.create_index(
                collection_name=self.collection,
                index_params=index_params,
            )
            self.client.load_collection(self.collection)
        except Exception as exc:
            # Milvus may raise if index already exists; this is harmless
            error_msg = str(exc).lower()
            if (
                "already exist" in error_msg
                or "duplicate" in error_msg
                or "at most one distinct index" in error_msg
            ):
                logger.debug(f"[KB] index already exists, skipping creation")
            else:
                logger.warning(
                    f"[KB] index creation skipped ({type(exc).__name__}): {exc}"
                )
        logger.info(
            f"[KB] created collection '{self.collection}' "
            f"(dim={self.embedding_dim}, metric=COSINE)"
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """从兼容 OpenAI 的端点获取嵌入向量。

        最多重试 3 次，失败后采用退避策略。
        """
        base_url = os.getenv("EMBEDDING_BASE_URL")
        api_key = os.getenv("EMBEDDING_API_KEY")
        if not base_url or not api_key:
            raise KBConfigError(
                "EMBEDDING_BASE_URL and EMBEDDING_API_KEY must be configured"
            )

        # 大多数兼容 OpenAI 的端点都支持 /v1/embeddings
        # 如果base URL 已经以 /v1 结尾，需要相应调整。
        if base_url.endswith("/v1"):
            url = f"{base_url}/embeddings"
        else:
            url = f"{base_url}/v1/embeddings"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.embedding_model,
            "input": texts,
        }

        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                logger.debug(f"[KB] embedding {len(texts)} texts via {url} (model={self.embedding_model}, attempt={attempt + 1})")
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                resp.raise_for_status()

                data = resp.json()
                embeddings = [item["embedding"] for item in data["data"]]
                # 按索引排序以保持顺序
                embeddings.sort(key=lambda x: x.get("index", 0) if isinstance(x, dict) else 0)
                result = [item["embedding"] if isinstance(item, dict) else item for item in embeddings]

                # 自动检测实际dim与配置dim的差异
                if result and len(result[0]) != self.embedding_dim:
                    logger.warning(
                        f"[KB] embedding dim mismatch: configured={self.embedding_dim}, "
                        f"actual={len(result[0])}. Update EMBEDDING_DIM env var."
                    )

                return result

            except requests.HTTPError as e:
                last_exc = e
                status = e.response.status_code if e.response is not None else 0

                # 不可恢复：认证/权限/参数错误 — 不重试
                if status in (401, 403):
                    logger.error(
                        f"[KB] embedding auth error HTTP {status}, not retrying: {e}"
                    )
                    raise KBEmbeddingFatalError(
                        f"Embedding API 认证/权限失败 (HTTP {status})"
                    ) from e
                if status == 400:
                    logger.error(
                        f"[KB] embedding bad request HTTP 400, not retrying: {e}"
                    )
                    raise KBEmbeddingFatalError(
                        f"Embedding API 参数错误 (HTTP 400)"
                    ) from e

                # 可恢复：429 / 5xx — 重试
                if status == 429 and attempt < 2:
                    wait = 3 * (attempt + 1)
                    logger.warning(f"[KB] embedding 429 rate-limited, retrying in {wait}s (attempt {attempt + 1}/3)")
                    time.sleep(wait)
                elif status >= 500 and attempt < 2:
                    wait = 2 * (attempt + 1)
                    logger.warning(f"[KB] embedding server error {status}, retrying in {wait}s (attempt {attempt + 1}/3)")
                    time.sleep(wait)
                else:
                    logger.error(f"[KB] embedding HTTP {status}, no more retries: {e}")

            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
                if attempt < 2:
                    wait = 1.5 * (attempt + 1)
                    logger.warning(f"[KB] embedding network error, retrying in {wait:.1f}s (attempt {attempt + 1}/3): {e}")
                    time.sleep(wait)
                else:
                    logger.error(f"[KB] embedding network error, no more retries: {e}")

            except (ValueError, KeyError, TypeError) as e:
                # JSON 解析 / 数据结构错误 — 永久错误，不重试
                logger.error(
                    f"[KB] embedding response parse error ({type(e).__name__}), "
                    f"not retrying: {e}"
                )
                raise KBEmbeddingFatalError(
                    f"Embedding 响应解析失败: {e}"
                ) from e

            except Exception as e:
                # 未知异常 — 保守重试
                last_exc = e
                if attempt < 2:
                    wait = 1.5 * (attempt + 1)
                    logger.warning(
                        f"[KB] embedding unexpected error ({type(e).__name__}), "
                        f"retrying in {wait:.1f}s (attempt {attempt + 1}/3): {e}"
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        f"[KB] embedding unexpected error ({type(e).__name__}), "
                        f"no more retries: {e}"
                    )

        raise RuntimeError(
            f"[KB] embedding failed after 3 attempts: {last_exc}"
        ) from last_exc

    async def _aembed(self, texts: list[str]) -> list[list[float]]:
        """异步 embedding——用 asyncio.to_thread 包裹同步方法，不阻塞事件循环."""
        return await asyncio.to_thread(self._embed, texts)
