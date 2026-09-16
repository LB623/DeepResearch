"""Behavior tests for the reproducible multimodal benchmark CLI."""

from __future__ import annotations

import json

from agent.retrieval import MediaAsset, SearchHit
from eval.run_multimodal_benchmark import main


def test_replay_cli_reports_media_quality_and_latency(tmp_path):
    dataset_path = tmp_path / "dataset.json"
    replay_path = tmp_path / "replay.json"
    output_path = tmp_path / "result.json"
    dataset_path.write_text(
        json.dumps(
            {
                "schema": "multimodal_retrieval_set_v1",
                "cases": [
                    {"case_id": "img", "query": "model diagram", "kind": "image"},
                    {"case_id": "vid", "query": "official demo", "kind": "video"},
                    {"case_id": "neg", "query": "API specification", "kind": "none"},
                ],
            }
        ),
        encoding="utf-8",
    )
    replay_path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "case_id": "img",
                        "repeat": 1,
                        "latency_seconds": 1.0,
                        "error_type": "",
                        "candidates": [
                            {"kind": "image", "metadata_relevance": 2},
                            {"kind": "image", "metadata_relevance": 1},
                            {"kind": "video", "metadata_relevance": 2},
                        ],
                    },
                    {
                        "case_id": "vid",
                        "repeat": 1,
                        "latency_seconds": 2.0,
                        "error_type": "",
                        "candidates": [{"kind": "video", "metadata_relevance": 2}],
                    },
                    {
                        "case_id": "neg",
                        "repeat": 1,
                        "latency_seconds": 3.0,
                        "error_type": "",
                        "candidates": [{"kind": "image", "metadata_relevance": 0}],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--dataset",
            str(dataset_path),
            "--replay",
            str(replay_path),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["aggregate"] == {
        "case_count": 3,
        "run_count": 3,
        "success_rate": 1.0,
        "positive_media_hit_rate": 1.0,
        "type_match_coverage_at_3": 1.0,
        "metadata_usable_coverage_at_3": 1.0,
        "metadata_precision_at_3": 1 / 3,
        "negative_media_leak_rate": 1.0,
        "latency_p50_seconds": 2.0,
        "latency_p95_seconds": 3.0,
        "errors": {},
    }
    assert result["by_kind"] == {
        "image": {
            "run_count": 1,
            "success_rate": 1.0,
            "media_hit_rate": 1.0,
            "type_match_coverage_at_3": 1.0,
            "metadata_usable_coverage_at_3": 1.0,
            "metadata_precision_at_3": 1 / 3,
        },
        "video": {
            "run_count": 1,
            "success_rate": 1.0,
            "media_hit_rate": 1.0,
            "type_match_coverage_at_3": 1.0,
            "metadata_usable_coverage_at_3": 1.0,
            "metadata_precision_at_3": 1 / 3,
        },
    }


class _FixtureSearchProvider:
    name = "fixture"

    async def search(self, query: str, limit: int) -> list[SearchHit]:
        assert query == "official model diagram"
        assert limit == 3
        return [
            SearchHit(
                title="Official model card",
                snippet="The requested architecture figure.",
                url="https://example.com/model-card",
                provider=self.name,
                source="official",
                media=(
                    MediaAsset(
                        url="https://cdn.example.com/architecture.png",
                        kind="image",
                    ),
                ),
            )
        ]


def test_live_cli_collects_through_search_provider_interface(tmp_path):
    dataset_path = tmp_path / "dataset.json"
    output_path = tmp_path / "result.json"
    dataset_path.write_text(
        json.dumps(
            {
                "schema": "multimodal_retrieval_set_v1",
                "cases": [
                    {
                        "case_id": "img",
                        "query": "official model diagram",
                        "kind": "image",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--dataset",
            str(dataset_path),
            "--output",
            str(output_path),
            "--repeats",
            "2",
            "--limit",
            "3",
        ],
        provider=_FixtureSearchProvider(),
    )

    assert exit_code == 0
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["run_config"] == {
        "repeats": 2,
        "limit": 3,
        "concurrency": 4,
        "wait_seconds": 3.0,
        "timeout_seconds": 12.0,
        "sources": [],
    }
    assert result["aggregate"]["run_count"] == 2
    assert result["aggregate"]["success_rate"] == 1.0
    assert result["aggregate"]["type_match_coverage_at_3"] == 1.0
    assert result["rows"][0]["candidates"] == [
        {
            "kind": "image",
            "title": "Official model card",
            "snippet": "The requested architecture figure.",
            "source": "official",
        }
    ]


class _FixtureMetadataJudge:
    model_id = "fixture-judge"

    def evaluate(self, candidates: list[dict[str, str]]):
        assert candidates == [
            {
                "id": "img:1:1",
                "query": "official model diagram",
                "expected_kind": "image",
                "returned_kind": "image",
                "title": "Official model card",
                "snippet": "The requested architecture figure.",
                "source": "official",
            }
        ]
        return {"img:1:1": 2}, {
            "calls": 1,
            "prompt_tokens": 20,
            "completion_tokens": 5,
            "total_tokens": 25,
        }


def test_live_cli_records_judge_quality_and_usage(tmp_path):
    dataset_path = tmp_path / "dataset.json"
    output_path = tmp_path / "result.json"
    dataset_path.write_text(
        json.dumps(
            {
                "schema": "multimodal_retrieval_set_v1",
                "cases": [
                    {
                        "case_id": "img",
                        "query": "official model diagram",
                        "kind": "image",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--dataset",
            str(dataset_path),
            "--output",
            str(output_path),
            "--limit",
            "3",
            "--repeats",
            "2",
            "--judge-model",
            "fixture-judge",
        ],
        provider=_FixtureSearchProvider(),
        judge=_FixtureMetadataJudge(),
    )

    assert exit_code == 0
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["aggregate"]["run_count"] == 2
    assert result["aggregate"]["metadata_usable_coverage_at_3"] == 1.0
    assert result["aggregate"]["metadata_precision_at_3"] == 1 / 3
    assert [row["candidates"][0]["metadata_relevance"] for row in result["rows"]] == [
        2,
        2,
    ]
    assert result["judge"] == {
        "model": "fixture-judge",
        "rubric": "strict metadata-only relevance; media content not inspected",
        "raw_candidate_count": 2,
        "evaluated_candidate_count": 1,
        "usage": {
            "calls": 1,
            "prompt_tokens": 20,
            "completion_tokens": 5,
            "total_tokens": 25,
        },
    }
