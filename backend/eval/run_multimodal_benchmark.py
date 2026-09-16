"""Reproducible benchmark for multimedia evidence retrieval.

The CLI can aggregate a frozen replay without external calls. Live collection and
LLM judging are added behind the same interface so paid runs stay explicit.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from dotenv import load_dotenv
from openai import OpenAI

from agent.llm.llm import _resolve_credentials
from agent.retrieval import (
    OmniSeekSearchProvider,
    SearchHit,
    SearchProvider,
    load_omniseek_credentials,
)

_KINDS = {"image", "video", "audio", "mixed", "none"}
_JUDGE_RUBRIC = "strict metadata-only relevance; media content not inspected"


class MetadataJudge(Protocol):
    model_id: str

    def evaluate(
        self, candidates: list[dict[str, str]]
    ) -> tuple[dict[str, int], dict[str, int]]: ...


class OpenAIMetadataJudge:
    """Strict metadata judge at the external LLM seam."""

    def __init__(self, model_id: str, *, batch_size: int = 20) -> None:
        load_dotenv(Path.cwd() / ".env")
        api_key, base_url = _resolve_credentials(model_id)
        if not api_key or not base_url:
            raise ValueError(f"judge credentials unavailable for model: {model_id}")
        self.model_id = model_id
        self._batch_size = max(1, min(batch_size, 50))
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)

    def evaluate(
        self, candidates: list[dict[str, str]]
    ) -> tuple[dict[str, int], dict[str, int]]:
        scores: dict[str, int] = {}
        usage = {
            "calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        for offset in range(0, len(candidates), self._batch_size):
            batch = candidates[offset : offset + self._batch_size]
            response = self._client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a strict retrieval evaluator. Return one JSON "
                            "object only and never infer unseen media content."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "task": (
                                    "Score whether each search result's title and "
                                    "snippet directly support that its attached media "
                                    "is about the requested topic."
                                ),
                                "rubric": {
                                    "2": "Directly relevant to the requested topic.",
                                    "1": "Related but indirect, generic, or uncertain.",
                                    "0": "Irrelevant or insufficient evidence.",
                                },
                                "output": {
                                    "judgments": [
                                        {
                                            "id": "candidate id",
                                            "metadata_relevance": "integer 0, 1, or 2",
                                        }
                                    ]
                                },
                                "candidates": batch,
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                temperature=0,
                response_format={"type": "json_object"},
                extra_body={"enable_thinking": False},
            )
            parsed = json.loads(response.choices[0].message.content or "{}")
            judgments = parsed.get("judgments", [])
            if not isinstance(judgments, list):
                raise ValueError("metadata judge returned an invalid judgment list")
            for judgment in judgments:
                if not isinstance(judgment, dict):
                    continue
                candidate_id = str(judgment.get("id") or "")
                value = judgment.get("metadata_relevance")
                if (
                    candidate_id
                    and isinstance(value, int)
                    and not isinstance(value, bool)
                    and 0 <= value <= 2
                ):
                    scores[candidate_id] = value
            response_usage = getattr(response, "usage", None)
            usage["calls"] += 1
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                usage[key] += int(getattr(response_usage, key, 0) or 0)
        return scores, usage


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def _load_cases(path: Path) -> dict[str, dict[str, str]]:
    payload = _load_json(path)
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("dataset must contain a non-empty cases list")
    cases: dict[str, dict[str, str]] = {}
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise ValueError("each dataset case must be an object")
        case_id = str(raw_case.get("case_id") or "").strip()
        query = str(raw_case.get("query") or "").strip()
        kind = str(raw_case.get("kind") or "").strip().casefold()
        if not case_id or not query or kind not in _KINDS:
            raise ValueError("dataset cases require case_id, query, and valid kind")
        if case_id in cases:
            raise ValueError(f"duplicate case_id: {case_id}")
        cases[case_id] = {"case_id": case_id, "query": query, "kind": kind}
    return cases


def _nearest_rank(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def _top_candidates(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw = row.get("candidates")
    if not isinstance(raw, list):
        return []
    return [item for item in raw[:3] if isinstance(item, dict)]


def _type_matches(expected: str, candidate: dict[str, Any]) -> bool:
    returned = str(candidate.get("kind") or "").casefold()
    return returned in {"image", "video", "audio"} and (
        expected == "mixed" or returned == expected
    )


def _is_direct(candidate: dict[str, Any]) -> bool:
    value = candidate.get("metadata_relevance")
    return isinstance(value, int) and not isinstance(value, bool) and value == 2


def _aggregate(
    cases: dict[str, dict[str, str]], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    if not rows:
        raise ValueError("replay must contain at least one row")
    latencies: list[float] = []
    errors: Counter[str] = Counter()
    success_count = 0
    positive_count = 0
    media_hit_count = 0
    type_match_count = 0
    usable_count = 0
    direct_candidates = 0
    negative_count = 0
    negative_media_count = 0

    for row in rows:
        case_id = str(row.get("case_id") or "")
        if case_id not in cases:
            raise ValueError(f"replay references unknown case_id: {case_id}")
        try:
            latency = float(row.get("latency_seconds", 0.0))
        except (TypeError, ValueError) as exc:
            raise ValueError("latency_seconds must be numeric") from exc
        latencies.append(max(0.0, latency))
        error_type = str(row.get("error_type") or "").strip()
        if error_type:
            errors[error_type] += 1
        else:
            success_count += 1

        expected = cases[case_id]["kind"]
        candidates = _top_candidates(row)
        if expected == "none":
            negative_count += 1
            negative_media_count += int(bool(candidates))
            continue

        positive_count += 1
        media_hit_count += int(bool(candidates))
        matching = [item for item in candidates if _type_matches(expected, item)]
        type_match_count += int(bool(matching))
        usable = [item for item in matching if _is_direct(item)]
        usable_count += int(bool(usable))
        direct_candidates += len(usable)

    return {
        "case_count": len(cases),
        "run_count": len(rows),
        "success_rate": success_count / len(rows),
        "positive_media_hit_rate": media_hit_count / positive_count,
        "type_match_coverage_at_3": type_match_count / positive_count,
        "metadata_usable_coverage_at_3": usable_count / positive_count,
        "metadata_precision_at_3": direct_candidates / (3 * positive_count),
        "negative_media_leak_rate": (
            negative_media_count / negative_count if negative_count else 0.0
        ),
        "latency_p50_seconds": statistics.median(latencies),
        "latency_p95_seconds": _nearest_rank(latencies, 0.95),
        "errors": dict(errors),
    }


def _aggregate_by_kind(
    cases: dict[str, dict[str, str]], rows: list[dict[str, Any]]
) -> dict[str, dict[str, int | float]]:
    result: dict[str, dict[str, int | float]] = {}
    for expected in ("image", "video", "audio", "mixed"):
        subset = [
            row
            for row in rows
            if cases[str(row.get("case_id") or "")]["kind"] == expected
        ]
        if not subset:
            continue
        success = 0
        media_hit = 0
        type_match = 0
        usable = 0
        direct = 0
        for row in subset:
            success += int(not str(row.get("error_type") or "").strip())
            candidates = _top_candidates(row)
            media_hit += int(bool(candidates))
            matching = [item for item in candidates if _type_matches(expected, item)]
            type_match += int(bool(matching))
            direct_items = [item for item in matching if _is_direct(item)]
            usable += int(bool(direct_items))
            direct += len(direct_items)
        count = len(subset)
        result[expected] = {
            "run_count": count,
            "success_rate": success / count,
            "media_hit_rate": media_hit / count,
            "type_match_coverage_at_3": type_match / count,
            "metadata_usable_coverage_at_3": usable / count,
            "metadata_precision_at_3": direct / (3 * count),
        }
    return result


def _safe_error_types(exc: BaseException) -> str:
    names: list[str] = []
    pending = [exc]
    while pending:
        current = pending.pop()
        names.append(type(current).__name__)
        nested = getattr(current, "exceptions", ())
        if isinstance(nested, tuple):
            pending.extend(item for item in nested if isinstance(item, BaseException))
    return "+".join(dict.fromkeys(names))


def _media_candidates(hits: Sequence[SearchHit]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for hit in hits:
        for asset in hit.media:
            candidates.append(
                {
                    "kind": asset.kind,
                    "title": hit.title,
                    "snippet": hit.snippet,
                    "source": hit.source or hit.provider,
                }
            )
            if len(candidates) >= 3:
                return candidates
    return candidates


def _judge_candidates(
    cases: dict[str, dict[str, str]], rows: list[dict[str, Any]]
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for row in rows:
        case_id = str(row["case_id"])
        repeat = int(row.get("repeat", 1))
        case = cases[case_id]
        for rank, candidate in enumerate(_top_candidates(row), start=1):
            candidates.append(
                {
                    "id": f"{case_id}:{repeat}:{rank}",
                    "query": case["query"],
                    "expected_kind": case["kind"],
                    "returned_kind": str(candidate.get("kind") or ""),
                    "title": str(candidate.get("title") or "")[:300],
                    "snippet": str(candidate.get("snippet") or "")[:700],
                    "source": str(candidate.get("source") or "")[:100],
                }
            )
    return candidates


def _deduplicate_judge_candidates(
    candidates: list[dict[str, str]],
) -> tuple[list[dict[str, str]], dict[str, list[str]]]:
    unique: list[dict[str, str]] = []
    representative_by_fingerprint: dict[str, str] = {}
    aliases: dict[str, list[str]] = {}
    for candidate in candidates:
        candidate_id = candidate["id"]
        fingerprint = json.dumps(
            {key: value for key, value in candidate.items() if key != "id"},
            ensure_ascii=False,
            sort_keys=True,
        )
        representative = representative_by_fingerprint.get(fingerprint)
        if representative is None:
            representative_by_fingerprint[fingerprint] = candidate_id
            aliases[candidate_id] = [candidate_id]
            unique.append(candidate)
        else:
            aliases[representative].append(candidate_id)
    return unique, aliases


def _apply_judgments(rows: list[dict[str, Any]], scores: dict[str, int]) -> None:
    for row in rows:
        case_id = str(row["case_id"])
        repeat = int(row.get("repeat", 1))
        for rank, candidate in enumerate(_top_candidates(row), start=1):
            candidate["metadata_relevance"] = scores.get(
                f"{case_id}:{repeat}:{rank}", 0
            )


async def _collect_one(
    *,
    case: dict[str, str],
    repeat: int,
    provider: SearchProvider,
    limit: int,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    async with semaphore:
        started = time.perf_counter()
        try:
            hits = await provider.search(case["query"], limit)
            error_type = ""
        except Exception as exc:
            hits = []
            error_type = _safe_error_types(exc)
        latency_seconds = time.perf_counter() - started
    return {
        "case_id": case["case_id"],
        "repeat": repeat,
        "latency_seconds": latency_seconds,
        "error_type": error_type,
        "candidates": _media_candidates(hits),
    }


async def _collect_rows(
    *,
    cases: dict[str, dict[str, str]],
    provider: SearchProvider,
    repeats: int,
    limit: int,
    concurrency: int,
) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        _collect_one(
            case=case,
            repeat=repeat,
            provider=provider,
            limit=limit,
            semaphore=semaphore,
        )
        for repeat in range(1, repeats + 1)
        for case in cases.values()
    ]
    rows = [await task for task in asyncio.as_completed(tasks)]
    return sorted(rows, key=lambda row: (str(row["case_id"]), int(row["repeat"])))


def _default_credentials_file() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "infrastructure"
        / "omniseek"
        / "data"
        / "credentials"
        / "omniseek_http.json"
    )


def _build_live_provider(args: argparse.Namespace) -> SearchProvider:
    load_dotenv(Path.cwd() / ".env")
    credentials = load_omniseek_credentials(
        default_token_file=_default_credentials_file()
    )
    if credentials is None:
        raise ValueError("OmniSeek credentials are unavailable")
    endpoint, token = credentials
    sources = tuple(
        source.strip() for source in str(args.sources).split(",") if source.strip()
    )
    return OmniSeekSearchProvider(
        endpoint=endpoint,
        token=token,
        wait_seconds=args.wait_seconds,
        request_timeout_seconds=args.timeout_seconds,
        sources=sources,
        max_results=args.limit,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate multimedia evidence retrieval on a frozen set."
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--wait-seconds", type=float, default=3.0)
    parser.add_argument("--timeout-seconds", type=float, default=12.0)
    parser.add_argument("--sources", default="")
    parser.add_argument("--judge-model", default="")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    provider: SearchProvider | None = None,
    judge: MetadataJudge | None = None,
) -> int:
    args = _parser().parse_args(argv)
    if args.repeats < 1 or args.limit < 1 or args.concurrency < 1:
        raise ValueError("repeats, limit, and concurrency must be positive")
    cases = _load_cases(args.dataset)
    if args.replay is not None:
        replay = _load_json(args.replay)
        raw_rows = replay.get("rows")
        if not isinstance(raw_rows, list):
            raise ValueError("replay must contain a rows list")
        rows = [row for row in raw_rows if isinstance(row, dict)]
    else:
        live_provider = provider or _build_live_provider(args)
        rows = asyncio.run(
            _collect_rows(
                cases=cases,
                provider=live_provider,
                repeats=args.repeats,
                limit=args.limit,
                concurrency=args.concurrency,
            )
        )
    judge_info: dict[str, Any] | None = None
    if judge is not None or args.judge_model:
        active_judge = judge or OpenAIMetadataJudge(args.judge_model)
        raw_judge_candidates = _judge_candidates(cases, rows)
        judge_candidates, aliases = _deduplicate_judge_candidates(raw_judge_candidates)
        representative_scores, usage = active_judge.evaluate(judge_candidates)
        scores = {
            candidate_id: representative_scores[representative]
            for representative, candidate_ids in aliases.items()
            if representative in representative_scores
            for candidate_id in candidate_ids
        }
        _apply_judgments(rows, scores)
        judge_info = {
            "model": active_judge.model_id,
            "rubric": _JUDGE_RUBRIC,
            "raw_candidate_count": len(raw_judge_candidates),
            "evaluated_candidate_count": len(judge_candidates),
            "usage": usage,
        }
    configured_sources = [
        source.strip() for source in str(args.sources).split(",") if source.strip()
    ]
    result = {
        "schema": "multimodal_retrieval_benchmark_v1",
        "dataset": args.dataset.name,
        "run_config": {
            "repeats": args.repeats,
            "limit": args.limit,
            "concurrency": args.concurrency,
            "wait_seconds": args.wait_seconds,
            "timeout_seconds": args.timeout_seconds,
            "sources": configured_sources,
        },
        "aggregate": _aggregate(cases, rows),
        "by_kind": _aggregate_by_kind(cases, rows),
        "rows": rows,
    }
    if judge_info is not None:
        result["judge"] = judge_info
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result["aggregate"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
