"""知识库生命周期模式——控制新鲜度过滤、置信度衰减和事实年龄标记。

四种运行模式：
  - off/关闭：不进行过滤、不衰减、不添加年龄标记。
  - inform/通知：添加年龄标记并更改措辞，但不进行过滤或衰减。
  - freshness/新鲜度：Plan LLM判定 → 统一的年龄过滤和衰减。
  - lifecycle/生命周期：事实类别 → 按类别进行生命周期时间 (TTL) 过滤和衰减。

模式从 KB_LIFECYCLE_MODE 环境变量读取（默认值为“freshness”）。

"""

from __future__ import annotations

import os
from enum import Enum


class KBLifecycleMode(str, Enum):
    OFF = "off"
    INFORM = "inform"
    FRESHNESS = "freshness"
    LIFECYCLE = "lifecycle"


# ── 统一年龄阈值 (freshness mode) ───────────────────────────
FRESHNESS_MAX_AGE: dict[str, int] = {
    "high": 7,
    "medium": 30,
    "low": 180,
}

# ── 按类别划分的 TTL (lifecycle mode) ─────────────────────────────────
CATEGORY_TTL: dict[str, int | None] = {
    "market_data": 7, # 市场数据——7天过期
    "product_info": 30, # 产品信息——30天
    "strategy": 90, # 战略方向——90天
    "technology": 180, # 技术定义——180天
    "historical": None,  # 历史事件——永不过期
}


def get_mode() -> KBLifecycleMode:
    """从环境变量中读取当前生命周期模式。

    如果值无效或未设置，则回退到 FRESHNESS。
    """
    raw = os.getenv("KB_LIFECYCLE_MODE", "freshness")
    try:
        return KBLifecycleMode(raw)
    except ValueError:
        return KBLifecycleMode.FRESHNESS


def should_filter(mode: KBLifecycleMode | None = None) -> bool:
    """当应该根据事实的时效性来排除事实时，返回 True"""
    if mode is None:
        mode = get_mode()
    return mode in (KBLifecycleMode.FRESHNESS, KBLifecycleMode.LIFECYCLE)


def should_decay(mode: KBLifecycleMode | None = None) -> bool:
    """当需要对置信度分数进行基于时间的衰减时，返回 True"""
    if mode is None:
        mode = get_mode()
    return mode in (KBLifecycleMode.FRESHNESS, KBLifecycleMode.LIFECYCLE)


def should_tag(mode: KBLifecycleMode | None = None) -> bool:
    """当需要给事实添加人类可读的时效性标签时，返回 True"""
    if mode is None:
        mode = get_mode()
    return mode != KBLifecycleMode.OFF


def should_warn(mode: KBLifecycleMode | None = None) -> bool:
    """当提示词（prompt）的措辞应该鼓励重新验证，而不是禁止重新搜索时，
    返回 True"""
    if mode is None:
        mode = get_mode()
    return mode != KBLifecycleMode.OFF
