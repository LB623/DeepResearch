"""Deterministic output-contract metrics for research reports.

This module does not call an LLM. It measures whether a finished report
can be traced back to gathered sources, and whether Writer guards reject
the failure modes they claim to catch.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

MARKDOWN_URL_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
HEADING_RE = re.compile(r"^(#{1,2})\s+(.+?)\s*$", re.MULTILINE)
CONCLUSION_RE = re.compile(r"结论|conclusion", re.IGNORECASE)
INTERNAL_LEFTOVER_RE = re.compile(
    r"(?:"
    r"\[ID\s*/?\s*\d+\s*-\s*\d+\]"
    r"|\[来源id/\d+-\d+\]"
    r"|\[(?:材料|material|source)\s*[-_:：]?\s*\d{1,3}\](?!\()"
    r"|(?:https?://)?search\.com/id/\d+-\d+"
    r")",
    re.IGNORECASE,
)

LONG_BODY = (
    "本节只使用检索材料中已经出现的陈述，并保持原有章节标题。"
    "补充数据口径、时间范围和来源边界，避免写入无法回源的专名或链接。"
) * 12

PLACEHOLDERS = {
    "$LONG": LONG_BODY,
}


@dataclass(frozen=True)
class ReportContractScore:
    topic: str
    char_count: int
    citation_count: int
    unique_url_count: int
    source_count: int
    unknown_url_count: int
    grounded_url_rate: float | None
    leftover_count: int
    heading_count: int
    has_conclusion: bool
    unknown_urls: list[str] = field(default_factory=list)
    leftover_samples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GuardCaseResult:
    case_id: str
    category: str
    check: str
    should_reject: bool
    rejected: bool
    reason: str
    correct: bool
    reason_ok: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def expand_placeholders(text: str) -> str:
    expanded = text or ""
    for token, value in PLACEHOLDERS.items():
        expanded = expanded.replace(token, value)
    return expanded


def parse_sources(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return loaded if isinstance(loaded, list) else []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def source_urls(sources: list[dict[str, Any]]) -> set[str]:
    urls: set[str] = set()
    for source in sources:
        for key in ("value", "short_url", "url"):
            value = source.get(key)
            if value:
                urls.add(str(value).strip())
    return urls


def extract_citation_urls(report: str) -> list[str]:
    return [url for _, url in MARKDOWN_URL_RE.findall(report or "")]


def find_internal_leftovers(report: str) -> list[str]:
    return [match.group(0) for match in INTERNAL_LEFTOVER_RE.finditer(report or "")]


def score_report_contract(
    report: str,
    sources: Any,
    *,
    topic: str = "",
) -> ReportContractScore:
    parsed_sources = parse_sources(sources)
    urls = extract_citation_urls(report)
    unique_urls = list(dict.fromkeys(urls))
    allowed = source_urls(parsed_sources)
    unknown = [url for url in unique_urls if url not in allowed]
    leftovers = find_internal_leftovers(report)
    headings = HEADING_RE.findall(report or "")
    unique_count = len(unique_urls)
    grounded_rate = (
        (unique_count - len(unknown)) / unique_count if unique_count else None
    )
    return ReportContractScore(
        topic=topic,
        char_count=len(report or ""),
        citation_count=len(urls),
        unique_url_count=unique_count,
        source_count=len(parsed_sources),
        unknown_url_count=len(unknown),
        grounded_url_rate=grounded_rate,
        leftover_count=len(leftovers),
        heading_count=len(headings),
        has_conclusion=any(CONCLUSION_RE.search(title) for _, title in headings),
        unknown_urls=unknown[:8],
        leftover_samples=list(dict.fromkeys(leftovers))[:8],
    )


def load_e2e_records(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("e2e_results")
    if not isinstance(records, list):
        raise ValueError(f"{path} has no e2e_results list")
    return [record for record in records if isinstance(record, dict)]


def score_e2e_file(path: Path) -> list[ReportContractScore]:
    scores: list[ReportContractScore] = []
    for record in load_e2e_records(path):
        scores.append(
            score_report_contract(
                str(record.get("report") or ""),
                record.get("sources"),
                topic=str(record.get("topic") or ""),
            )
        )
    return scores


def summarize_contract_scores(
    label: str,
    scores: list[ReportContractScore],
) -> dict[str, Any]:
    grounded = [item.grounded_url_rate for item in scores if item.grounded_url_rate is not None]
    return {
        "label": label,
        "n": len(scores),
        "mean_grounded_url_rate": (
            sum(grounded) / len(grounded) if grounded else None
        ),
        "topics_with_unknown_url": sum(
            1 for item in scores if item.unknown_url_count > 0
        ),
        "topics_with_leftover": sum(1 for item in scores if item.leftover_count > 0),
        "total_unknown_urls": sum(item.unknown_url_count for item in scores),
        "total_leftovers": sum(item.leftover_count for item in scores),
        "topics_missing_conclusion": sum(
            1 for item in scores if not item.has_conclusion
        ),
        "per_topic": [item.to_dict() for item in scores],
    }


def load_guard_corpus(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"{path} has no cases")
    return cases


def score_guard_case(case: dict[str, Any]) -> GuardCaseResult:
    previous_checkpoint_backend = os.environ.get("CHECKPOINT_BACKEND")
    os.environ["CHECKPOINT_BACKEND"] = "none"
    try:
        from agent.sub_agents.writer_agent import (
            _draft_rejection_reason,
            _polish_rejection_reason,
            _unsupported_named_terms,
        )
    finally:
        if previous_checkpoint_backend is None:
            os.environ.pop("CHECKPOINT_BACKEND", None)
        else:
            os.environ["CHECKPOINT_BACKEND"] = previous_checkpoint_backend

    check = str(case.get("check") or "polish")
    draft = expand_placeholders(str(case.get("draft") or ""))
    polished = expand_placeholders(str(case.get("polished") or ""))
    outline = expand_placeholders(str(case.get("outline") or ""))
    evidence = expand_placeholders(str(case.get("evidence") or ""))
    topic = str(case.get("research_topic") or "")
    sources = parse_sources(case.get("sources"))
    should_reject = bool(case.get("should_reject"))
    expected_fragment = str(case.get("reason_contains") or "")

    if check == "polish":
        reason = _polish_rejection_reason(draft, polished, sources) or ""
        rejected = bool(reason)
    elif check == "draft":
        reason = _draft_rejection_reason(outline, draft) or ""
        rejected = bool(reason)
    elif check == "unsupported_terms":
        terms = _unsupported_named_terms(
            draft,
            evidence=evidence,
            research_topic=topic,
        )
        reason = ", ".join(terms)
        rejected = bool(terms)
    elif check == "contract":
        score = score_report_contract(polished or draft, sources, topic=topic)
        leftover_expected = bool(case.get("expect_leftover", False))
        unknown_expected = bool(case.get("expect_unknown_url", False))
        if leftover_expected:
            rejected = score.leftover_count > 0
        elif unknown_expected:
            rejected = score.unknown_url_count > 0
        else:
            rejected = score.leftover_count > 0 or score.unknown_url_count > 0
        reason = (
            f"leftovers={score.leftover_count}; "
            f"unknown_urls={score.unknown_url_count}"
        )
    else:
        raise ValueError(f"unsupported check={check!r} in case {case.get('id')}")

    reason_ok = (not expected_fragment) or (expected_fragment in reason)
    correct = (rejected == should_reject) and reason_ok
    return GuardCaseResult(
        case_id=str(case.get("id") or ""),
        category=str(case.get("category") or ""),
        check=check,
        should_reject=should_reject,
        rejected=rejected,
        reason=reason,
        correct=correct,
        reason_ok=reason_ok,
    )


def summarize_guard_results(results: list[GuardCaseResult]) -> dict[str, Any]:
    positives = [item for item in results if item.should_reject]
    negatives = [item for item in results if not item.should_reject]
    by_category: dict[str, list[GuardCaseResult]] = {}
    for item in results:
        by_category.setdefault(item.category, []).append(item)

    category_rows = []
    for category, items in sorted(by_category.items()):
        cat_pos = [item for item in items if item.should_reject]
        cat_neg = [item for item in items if not item.should_reject]
        category_rows.append(
            {
                "category": category,
                "n": len(items),
                "recall": (
                    sum(item.rejected for item in cat_pos) / len(cat_pos)
                    if cat_pos
                    else None
                ),
                "false_positive_rate": (
                    sum(item.rejected for item in cat_neg) / len(cat_neg)
                    if cat_neg
                    else None
                ),
                "accuracy": sum(item.correct for item in items) / len(items),
            }
        )

    return {
        "n": len(results),
        "recall": (
            sum(item.rejected for item in positives) / len(positives)
            if positives
            else None
        ),
        "false_positive_rate": (
            sum(item.rejected for item in negatives) / len(negatives)
            if negatives
            else None
        ),
        "accuracy": (
            sum(item.correct for item in results) / len(results) if results else None
        ),
        "reason_mismatch": sum(not item.reason_ok for item in results),
        "by_category": category_rows,
        "failures": [item.to_dict() for item in results if not item.correct],
        "label_counts": dict(Counter(item.category for item in results)),
        "results": [item.to_dict() for item in results],
    }
