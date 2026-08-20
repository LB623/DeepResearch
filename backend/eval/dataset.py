"""Fixed E2E dataset schema, vocabularies, and loader.

This module is offline: it only reads JSON files and validates structure.
It does not call an LLM, web search, Milvus, or embedding service.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eval.evaluator import TopicCfg

EVAL_DIR = Path(__file__).resolve().parent
CANONICAL_E2E_SET = "test_set_e2e.json"
BASIC_FIVE_SET = "test_set_basic_5.json"
CANONICAL_DATASET_NAME = "e2e_fixed_v2"
CANONICAL_FROZEN_AT = "2026-06-30"
CANONICAL_AS_OF = "2026-06-30"

TIERS = ("smoke", "core", "full")
TIER_RANK = {"smoke": 0, "core": 1, "full": 2}

DOMAINS = (
    "ai_tech",
    "policy_law",
    "science_health",
    "energy_climate",
    "finance_macro",
    "security_safety",
    "society_org",
    "methods",
)

EVALUATION_FOCUS = (
    "false_premise",
    "source_conflict",
    "stat_definition",
    "legal_timeline",
    "evidence_grading",
    "causal_vs_correlational",
    "long_tail_retrieval",
    "cross_lingual_sources",
    "abstention",
    "primary_sources",
)

DIFFICULTIES = ("easy", "medium", "hard")

RISK_FLAGS = (
    "hallucination_prone",
    "false_premise",
    "stale_date",
    "vendor_bias",
    "thin_evidence",
    "numeric_conflict",
    "jurisdiction_mix",
)

SOURCE_LANGUAGES = ("zh", "en", "ja", "ko", "de", "fr", "pt", "es")

REQUIRED_CASE_FIELDS = (
    "case_id",
    "topic",
    "tier",
    "domain",
    "difficulty",
    "evaluation_focus",
    "initial_search_query_count",
    "max_research_loops",
)


@dataclass
class DatasetMeta:
    name: str = ""
    description: str = ""
    frozen_at: str = ""
    as_of: str = ""
    path: str = ""


@dataclass
class LoadedSet:
    meta: DatasetMeta
    cases: list[TopicCfg] = field(default_factory=list)
    raw_topics: list[dict[str, Any]] = field(default_factory=list)


def resolve_test_set_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    nested = EVAL_DIR / candidate
    if nested.exists():
        return nested
    cwd_candidate = Path.cwd() / candidate
    if cwd_candidate.exists():
        return cwd_candidate
    return nested


def case_in_tier(case_tier: str, selected: str) -> bool:
    if selected not in TIER_RANK:
        raise ValueError(f"unknown tier: {selected}")
    if not case_tier:
        return False
    if case_tier not in TIER_RANK:
        raise ValueError(f"unknown case tier: {case_tier}")
    return TIER_RANK[case_tier] <= TIER_RANK[selected]


def select_tier(cases: list[TopicCfg], tier: str) -> list[TopicCfg]:
    return [case for case in cases if case_in_tier(case.tier, tier)]


def topic_cfg_from_item(
    item: dict[str, Any],
    *,
    index: int,
    default_as_of: str = "",
) -> TopicCfg:
    from eval.evaluator import TopicCfg
    source_expectations = item.get("source_expectations") or {}
    if source_expectations and not isinstance(source_expectations, dict):
        raise ValueError(f"source_expectations must be an object: {item.get('case_id')}")
    case_id = str(item.get("case_id") or "").strip()
    if not case_id:
        case_id = f"e2e-adhoc-{index:03d}"
    return TopicCfg(
        topic=item["topic"],
        initial_search_query_count=int(item.get("initial_search_query_count", 2)),
        max_research_loops=int(item.get("max_research_loops", 2)),
        user_feedback=item.get("user_feedback"),
        expected_intent=item.get("expected_intent"),
        case_id=case_id,
        tier=str(item.get("tier") or ""),
        domain=str(item.get("domain") or ""),
        difficulty=str(item.get("difficulty") or ""),
        evaluation_focus=[str(flag) for flag in item.get("evaluation_focus") or []],
        as_of=str(item.get("as_of") or default_as_of or ""),
        required_aspects=[str(flag) for flag in item.get("required_aspects") or []],
        risk_flags=[str(flag) for flag in item.get("risk_flags") or []],
        source_expectations=dict(source_expectations),
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_canonical_dataset(data: dict[str, Any]) -> None:
    topics = data.get("topics")
    _require(isinstance(topics, list), "canonical dataset missing topics list")
    _require(data.get("name") == CANONICAL_DATASET_NAME, "unexpected canonical dataset name")
    _require(data.get("frozen_at") == CANONICAL_FROZEN_AT, "unexpected frozen_at")
    _require(data.get("as_of") == CANONICAL_AS_OF, "unexpected dataset as_of")
    _require(len(topics) == 100, f"canonical dataset must have 100 cases, got {len(topics)}")

    case_ids: list[str] = []
    topic_texts: list[str] = []
    for index, item in enumerate(topics, start=1):
        _require(isinstance(item, dict), f"case {index} is not an object")
        for field_name in REQUIRED_CASE_FIELDS:
            _require(field_name in item, f"{item.get('case_id', index)} missing {field_name}")
        case_id = item["case_id"]
        _require(case_id == f"e2e-{index:03d}", f"case_id must be e2e-{index:03d}, got {case_id}")
        case_ids.append(case_id)
        topic_texts.append(item["topic"])
        _require(item["tier"] in TIERS, f"{case_id} has invalid tier {item['tier']}")
        _require(item["domain"] in DOMAINS, f"{case_id} has invalid domain {item['domain']}")
        _require(
            item["difficulty"] in DIFFICULTIES,
            f"{case_id} has invalid difficulty {item['difficulty']}",
        )
        focuses = item["evaluation_focus"]
        _require(isinstance(focuses, list) and focuses, f"{case_id} needs evaluation_focus")
        _require(len(focuses) <= 3, f"{case_id} has too many evaluation_focus tags")
        unknown_focus = [flag for flag in focuses if flag not in EVALUATION_FOCUS]
        _require(not unknown_focus, f"{case_id} has unknown evaluation_focus {unknown_focus}")
        risk_flags = item.get("risk_flags") or []
        unknown_risk = [flag for flag in risk_flags if flag not in RISK_FLAGS]
        _require(not unknown_risk, f"{case_id} has unknown risk_flags {unknown_risk}")
        _require(
            1 <= int(item["initial_search_query_count"]) <= 5,
            f"{case_id} query count out of range",
        )
        _require(
            1 <= int(item["max_research_loops"]) <= 10,
            f"{case_id} loop count out of range",
        )
        as_of = item.get("as_of") or data.get("as_of")
        _require(as_of == CANONICAL_AS_OF, f"{case_id} as_of must stay frozen at {CANONICAL_AS_OF}")
        expectations = item.get("source_expectations") or {}
        _require(isinstance(expectations, dict), f"{case_id} source_expectations must be an object")
        languages = expectations.get("languages") or []
        unknown_lang = [lang for lang in languages if lang not in SOURCE_LANGUAGES]
        _require(not unknown_lang, f"{case_id} has unknown source language {unknown_lang}")

    _require(len(set(case_ids)) == 100, "case_id values are not unique")
    _require(len(set(topic_texts)) == 100, "topic texts are not unique")

    nested = {
        "smoke": sum(1 for item in topics if case_in_tier(item["tier"], "smoke")),
        "core": sum(1 for item in topics if case_in_tier(item["tier"], "core")),
        "full": sum(1 for item in topics if case_in_tier(item["tier"], "full")),
    }
    _require(nested["smoke"] == 5, f"smoke must be 5 cases, got {nested['smoke']}")
    _require(nested["core"] == 30, f"core must be 30 cases, got {nested['core']}")
    _require(nested["full"] == 100, f"full must be 100 cases, got {nested['full']}")

    domain_counts = {domain: 0 for domain in DOMAINS}
    for item in topics:
        domain_counts[item["domain"]] += 1
    missing_domains = [domain for domain, count in domain_counts.items() if count == 0]
    _require(not missing_domains, f"missing domains: {missing_domains}")
    oversized = {domain: count for domain, count in domain_counts.items() if count > 20}
    _require(not oversized, f"domain imbalance: {oversized}")

    core_focus = {
        flag
        for item in topics
        if case_in_tier(item["tier"], "core")
        for flag in item["evaluation_focus"]
    }
    missing_core_focus = [flag for flag in EVALUATION_FOCUS if flag not in core_focus]
    _require(not missing_core_focus, f"core is missing capabilities: {missing_core_focus}")


def load_dataset(
    path: str | Path = CANONICAL_E2E_SET,
    *,
    tier: str | None = None,
    offset: int = 0,
    limit: int | None = None,
    strict: bool | None = None,
) -> LoadedSet:
    full_path = resolve_test_set_path(path)
    if not full_path.exists():
        raise FileNotFoundError(f"test set not found: {full_path}")
    data = json.loads(full_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"test set must be a JSON object: {full_path}")

    is_canonical = data.get("name") == CANONICAL_DATASET_NAME
    if strict is None:
        strict = is_canonical
    if strict:
        validate_canonical_dataset(data)

    meta = DatasetMeta(
        name=str(data.get("name") or ""),
        description=str(data.get("description") or ""),
        frozen_at=str(data.get("frozen_at") or ""),
        as_of=str(data.get("as_of") or ""),
        path=str(full_path),
    )
    cases = [
        topic_cfg_from_item(item, index=index, default_as_of=meta.as_of)
        for index, item in enumerate(data.get("topics") or [], start=1)
    ]
    if tier:
        if not any(case.tier for case in cases):
            raise ValueError(f"{full_path} has no tier metadata; cannot filter by --tier")
        cases = select_tier(cases, tier)
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be > 0")
    end = None if limit is None else offset + limit
    return LoadedSet(meta=meta, cases=cases[offset:end], raw_topics=list(data.get("topics") or []))


def load_basic_five() -> list[dict[str, Any]]:
    path = EVAL_DIR / BASIC_FIVE_SET
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("topics") or [])


def with_runtime_overrides(
    cases: list[TopicCfg],
    *,
    initial_queries: int | None = None,
    max_loops: int | None = None,
) -> list[TopicCfg]:
    if initial_queries is None and max_loops is None:
        return cases
    updated: list[TopicCfg] = []
    for case in cases:
        updated.append(
            replace(
                case,
                initial_search_query_count=(
                    initial_queries
                    if initial_queries is not None
                    else case.initial_search_query_count
                ),
                max_research_loops=(
                    max_loops if max_loops is not None else case.max_research_loops
                ),
            )
        )
    return updated
