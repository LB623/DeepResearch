"""Deterministic controlled corpus for the Milvus retrieval benchmark.

The corpus is synthetic by design: it measures ranking, lifecycle filtering,
and duplicate suppression without making claims about real-world facts.  The
logical dataset is stable across runs; ``created_at`` is materialized relative
to the run time so TTL boundary cases do not drift as the repository ages.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

DATASET_VERSION = "retrieval-controlled-v2"
DATASET_QUERY_COUNT = 100
DATASET_FACT_COUNT = 1_000
DEV_CASES_PER_DOMAIN = 6


@dataclass(frozen=True)
class RetrievalCase:
    """One query with graded relevance labels and frozen split metadata."""

    query: str
    relevant: dict[str, int]
    query_id: str = "adhoc"
    domain: str = "adhoc"
    split: str = "test"
    difficulty: str = "adhoc"


@dataclass(frozen=True)
class DomainSpec:
    """Language templates and lifecycle policy for one benchmark domain."""

    code: str
    category: str
    entity_label: str
    entity_prefixes: tuple[str, ...]
    field_labels: tuple[str, str, str, str, str]
    field_labels_en: tuple[str, str, str, str, str]
    ttl_days: int | None


DOMAIN_SPECS: tuple[DomainSpec, ...] = (
    DomainSpec(
        code="technology",
        category="technology",
        entity_label="技术服务",
        entity_prefixes=(
            "Aster",
            "Boreal",
            "Cinder",
            "Delta",
            "Ember",
            "Fjord",
            "Glint",
            "Helix",
            "Ion",
            "Juniper",
            "Kite",
            "Lumen",
            "Mosaic",
            "Nimbus",
            "Orchid",
            "Prism",
            "Quartz",
            "Raven",
            "Solace",
            "Tundra",
        ),
        field_labels=("索引模式", "并发上限", "调用协议", "部署区域", "延迟目标"),
        field_labels_en=(
            "index mode",
            "concurrency",
            "protocol",
            "region",
            "latency target",
        ),
        ttl_days=180,
    ),
    DomainSpec(
        code="product_info",
        category="product_info",
        entity_label="软件产品",
        entity_prefixes=(
            "Arc",
            "Beacon",
            "Canvas",
            "Drift",
            "Echo",
            "Fluent",
            "Grove",
            "Harbor",
            "Iris",
            "Jade",
            "Keystone",
            "Lotus",
            "Meadow",
            "Nova",
            "Orbit",
            "Pulse",
            "Quest",
            "Relay",
            "Slate",
            "Trace",
        ),
        field_labels=("当前版本", "核心功能", "支持平台", "发布渠道", "使用限制"),
        field_labels_en=(
            "current version",
            "core feature",
            "platform",
            "release channel",
            "usage limit",
        ),
        ttl_days=30,
    ),
    DomainSpec(
        code="market_data",
        category="market_data",
        entity_label="市场指标",
        entity_prefixes=(
            "ALP",
            "BRV",
            "CRN",
            "DAX",
            "ELM",
            "FRN",
            "GLD",
            "HZN",
            "IVY",
            "JCT",
            "KAP",
            "LNX",
            "MTR",
            "NRD",
            "OPL",
            "PRL",
            "QNT",
            "RIV",
            "STL",
            "TRN",
        ),
        field_labels=("统计周期", "指标值", "同比变化", "覆盖区域", "数据口径"),
        field_labels_en=(
            "period",
            "metric value",
            "year-on-year change",
            "region",
            "methodology",
        ),
        ttl_days=7,
    ),
    DomainSpec(
        code="strategy",
        category="strategy",
        entity_label="战略项目",
        entity_prefixes=(
            "Atlas",
            "Bridge",
            "Compass",
            "Dawn",
            "Everest",
            "Forge",
            "Gateway",
            "Horizon",
            "Insight",
            "Journey",
            "Kernel",
            "Lighthouse",
            "Meridian",
            "Northstar",
            "Odyssey",
            "Pioneer",
            "Quarry",
            "Roadmap",
            "Summit",
            "Trail",
        ),
        field_labels=("优先目标", "重点区域", "规划周期", "实施渠道", "主要风险"),
        field_labels_en=(
            "priority",
            "focus region",
            "planning horizon",
            "delivery channel",
            "main risk",
        ),
        ttl_days=90,
    ),
    DomainSpec(
        code="historical",
        category="historical",
        entity_label="历史项目",
        entity_prefixes=(
            "Archive",
            "Bastion",
            "Chronicle",
            "Dynasty",
            "Epoch",
            "Fossil",
            "Genesis",
            "Heritage",
            "Insignia",
            "Jubilee",
            "Legacy",
            "Monument",
            "Origin",
            "Parchment",
            "Relic",
            "Saga",
            "Timeline",
            "Unity",
            "Vintage",
            "Witness",
        ),
        field_labels=("发生年份", "发生地点", "关键里程碑", "参与角色", "后续影响"),
        field_labels_en=("year", "location", "milestone", "participants", "impact"),
        ttl_days=None,
    ),
)

DIFFICULTIES = ("keyword", "paraphrase", "compound", "cross_language", "short")
REGIONS = ("华东", "华南", "华北", "西南", "欧洲", "北美", "东南亚", "全球")
CHANNELS = ("稳定版", "灰度版", "企业版", "开发者预览版")
PROTOCOLS = ("HTTP/2", "gRPC", "WebSocket", "REST")


def _entity(spec: DomainSpec, index: int) -> str:
    return f"{spec.entity_prefixes[index]}-{index + 1:02d}"


def _field_values(spec: DomainSpec, index: int) -> tuple[str, str, str, str, str]:
    """Build five complementary values for one controlled entity."""
    region = REGIONS[index % len(REGIONS)]
    if spec.code == "technology":
        return (
            ("混合索引" if index % 2 == 0 else "分层索引"),
            f"{32 + index * 4} 路",
            PROTOCOLS[index % len(PROTOCOLS)],
            region,
            f"P95 小于 {40 + index * 3} ms",
        )
    if spec.code == "product_info":
        return (
            f"v{2 + index // 8}.{index % 8}.{index % 3}",
            ("跨文档检索" if index % 2 == 0 else "增量同步"),
            ("macOS 与 Linux" if index % 3 == 0 else "Web 与 Windows"),
            CHANNELS[index % len(CHANNELS)],
            f"单工作区最多 {20 + index * 5} 个数据源",
        )
    if spec.code == "market_data":
        return (
            f"2026 年第 {(index % 4) + 1} 季度",
            f"{120 + index * 7}.{index % 10} 点",
            f"{(-6 + index) / 2:+.1f}%",
            region,
            ("可比口径" if index % 2 == 0 else "经季节调整口径"),
        )
    if spec.code == "strategy":
        return (
            ("提升企业采用率" if index % 2 == 0 else "完善开发者生态"),
            region,
            f"{2 + index % 4} 个季度",
            ("合作伙伴渠道" if index % 3 == 0 else "直营与云市场"),
            ("数据合规" if index % 2 == 0 else "交付能力不足"),
        )
    return (
        str(1980 + index * 2),
        region,
        ("完成首次公开验证" if index % 2 == 0 else "发布首个稳定版本"),
        ("三家研究机构" if index % 3 == 0 else "跨地区工程团队"),
        ("形成后续标准草案" if index % 2 == 0 else "推动同类系统普及"),
    )


def _query(
    spec: DomainSpec, entity: str, values: tuple[str, ...], index: int
) -> tuple[str, str]:
    difficulty = DIFFICULTIES[index % len(DIFFICULTIES)]
    labels = spec.field_labels
    if difficulty == "keyword":
        query = f"{entity} {labels[0]} {labels[1]} {labels[2]}"
    elif difficulty == "paraphrase":
        query = f"请概括{entity}目前的配置、覆盖范围和约束"
    elif difficulty == "compound":
        query = f"{entity}的{labels[0]}是什么，并说明{labels[3]}与{labels[4]}"
    elif difficulty == "cross_language":
        query = (
            f"{entity} latest {spec.field_labels_en[0]}, "
            f"{spec.field_labels_en[2]} and {spec.field_labels_en[4]}"
        )
    else:
        query = f"{entity} 当前情况"
    return query, difficulty


def _age_days(spec: DomainSpec, *, stale: bool, index: int) -> int:
    if spec.ttl_days is None:
        return 3650 if stale else 1200 + index
    if stale:
        return spec.ttl_days + 1 + index % 3
    return max(1, min(spec.ttl_days - 1, 1 + index % 5))


def _fact(
    *,
    fact_id: str,
    text: str,
    topic: str,
    category: str,
    confidence: float,
    age_days: int,
    now: int,
) -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "fact": text,
        "source_url": f"https://benchmark.local/{fact_id}",
        "research_topic": topic,
        "confidence": confidence,
        "fact_category": category,
        "created_at": now - age_days * 86400,
        "logical_age_days": age_days,
    }


def _case_records(
    spec: DomainSpec,
    *,
    domain_index: int,
    case_index: int,
    now: int,
) -> tuple[list[dict[str, Any]], RetrievalCase]:
    entity = _entity(spec, case_index)
    neighbor = _entity(spec, (case_index + 1) % len(spec.entity_prefixes))
    values = _field_values(spec, case_index)
    query, difficulty = _query(spec, entity, values, case_index)
    query_id = f"{spec.code}-{case_index + 1:02d}"
    split = "dev" if case_index < DEV_CASES_PER_DOMAIN else "test"

    relevant_texts = [
        f"{entity}的{label}为{value}。"
        for label, value in zip(spec.field_labels, values, strict=True)
    ]
    relevant = {
        relevant_texts[0]: 3,
        relevant_texts[1]: 3,
        relevant_texts[2]: 2,
        relevant_texts[3]: 2,
        relevant_texts[4]: 1,
    }

    stale_value = f"旧值-{domain_index + 1}-{case_index + 1}"
    wrong_value = f"其他口径-{case_index + 7}"
    records = [
        _fact(
            fact_id=f"{query_id}-rel-{rank}",
            text=text,
            topic=query,
            category=spec.category,
            confidence=0.94 - rank * 0.025,
            age_days=_age_days(spec, stale=False, index=case_index + rank),
            now=now,
        )
        for rank, text in enumerate(relevant_texts, start=1)
    ]
    records.extend(
        [
            _fact(
                fact_id=f"{query_id}-duplicate-exact",
                text=relevant_texts[0],
                topic=query,
                category=spec.category,
                confidence=0.92,
                age_days=_age_days(spec, stale=False, index=case_index),
                now=now,
            ),
            _fact(
                fact_id=f"{query_id}-duplicate-format",
                text=relevant_texts[0].replace("。", " ！"),
                topic=query,
                category=spec.category,
                confidence=0.90,
                age_days=_age_days(spec, stale=False, index=case_index),
                now=now,
            ),
            _fact(
                fact_id=f"{query_id}-stale",
                text=f"{entity}的{spec.field_labels[0]}曾为{stale_value}。",
                topic=query,
                category=spec.category,
                confidence=0.99,
                age_days=_age_days(spec, stale=True, index=case_index),
                now=now,
            ),
            _fact(
                fact_id=f"{query_id}-conflict",
                text=f"{entity}的{spec.field_labels[1]}为{wrong_value}。",
                topic=query,
                category=spec.category,
                confidence=0.58,
                age_days=_age_days(spec, stale=False, index=case_index),
                now=now,
            ),
            _fact(
                fact_id=f"{query_id}-neighbor",
                text=f"{neighbor}的{spec.field_labels[0]}为{values[0]}。",
                topic=f"{neighbor} {spec.field_labels[0]}",
                category=spec.category,
                confidence=0.96,
                age_days=_age_days(spec, stale=False, index=case_index),
                now=now,
            ),
        ]
    )
    case = RetrievalCase(
        query=query,
        relevant=relevant,
        query_id=query_id,
        domain=spec.code,
        split=split,
        difficulty=difficulty,
    )
    return records, case


def build_fixed_set(
    *, now: int | None = None
) -> tuple[list[dict[str, Any]], list[RetrievalCase]]:
    """Return the 100-query, 1,000-fact deterministic controlled corpus."""
    materialized_now = int(time.time()) if now is None else now
    facts: list[dict[str, Any]] = []
    cases: list[RetrievalCase] = []
    for domain_index, spec in enumerate(DOMAIN_SPECS):
        for case_index in range(len(spec.entity_prefixes)):
            case_facts, case = _case_records(
                spec,
                domain_index=domain_index,
                case_index=case_index,
                now=materialized_now,
            )
            facts.extend(case_facts)
            cases.append(case)

    if len(facts) != DATASET_FACT_COUNT or len(cases) != DATASET_QUERY_COUNT:
        raise AssertionError(
            f"dataset contract violated: facts={len(facts)}, cases={len(cases)}"
        )
    return facts, cases


def dataset_hash(facts: list[dict[str, Any]], cases: list[RetrievalCase]) -> str:
    """Hash the logical corpus while excluding run-relative timestamps."""
    payload = {
        "version": DATASET_VERSION,
        "facts": [
            {key: value for key, value in fact.items() if key != "created_at"}
            for fact in facts
        ],
        "cases": [
            {
                "query_id": case.query_id,
                "query": case.query,
                "relevant": case.relevant,
                "domain": case.domain,
                "split": case.split,
                "difficulty": case.difficulty,
            }
            for case in cases
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
