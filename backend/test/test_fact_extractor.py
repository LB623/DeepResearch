"""Tests for FactExtractor — LLM-based fact extraction from summaries."""

import json
import pytest
from unittest.mock import MagicMock, patch


class TestFactExtractor:
    def test_extract_with_valid_summary(self):
        from agent.kb.extractor import FactExtractor

        facts_json = json.dumps([
            {"fact": "AI芯片市场2025年达500亿美元", "source_url": "https://search.com/id/0-0", "confidence": 0.9},
            {"fact": "NVIDIA占据80%市场份额", "source_url": "https://search.com/id/0-1", "confidence": 0.85},
        ])

        with patch("agent.kb.extractor.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.step.return_value = f"```json\n{facts_json}\n```"
            mock_agent_cls.return_value = mock_agent

            extractor = FactExtractor()
            result = extractor.extract(
                summary="AI芯片市场2025年达到500亿美元规模，NVIDIA占据80%市场份额。这些数据来源于多家研究机构的报告。" * 3,
                research_topic="AI芯片市场分析",
            )

            assert len(result) == 2
            assert result[0]["fact"] == "AI芯片市场2025年达500亿美元"
            assert result[0]["confidence"] == 0.9
            assert result[1]["confidence"] == 0.85

    def test_extract_short_summary_skipped(self):
        from agent.kb.extractor import FactExtractor

        extractor = FactExtractor()
        result = extractor.extract(summary="short", research_topic="test")
        assert result == []

    def test_extract_empty_summary_skipped(self):
        from agent.kb.extractor import FactExtractor

        extractor = FactExtractor()
        result = extractor.extract(summary="", research_topic="test")
        assert result == []

    def test_extract_validation_filters_invalid_facts(self):
        from agent.kb.extractor import FactExtractor

        facts_json = json.dumps([
            {"fact": "valid fact with enough length", "source_url": "https://s.com", "confidence": 0.8},
            {"fact": "sh", "source_url": "https://s.com", "confidence": 0.5},  # too short (<10 chars)
            {"fact": "", "source_url": "https://s.com", "confidence": 0.5},  # empty
            {"fact": "another valid fact here", "source_url": "https://s.com", "confidence": 1.5},  # confidence capped at 1.0
        ])

        with patch("agent.kb.extractor.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.step.return_value = f"```json\n{facts_json}\n```"
            mock_agent_cls.return_value = mock_agent

            extractor = FactExtractor()
            result = extractor.extract(
                summary="Long enough summary text with sufficient length. " * 10,
                research_topic="test",
            )

            assert len(result) == 2  # only the valid ones
            # confidence should be capped at 1.0
            assert result[1]["confidence"] == 1.0

    def test_extract_max_10_facts(self):
        from agent.kb.extractor import FactExtractor

        facts = [{"fact": f"fact number {i} with enough chars", "source_url": "https://s.com", "confidence": 0.8} for i in range(15)]
        facts_json = json.dumps(facts)

        with patch("agent.kb.extractor.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.step.return_value = f"```json\n{facts_json}\n```"
            mock_agent_cls.return_value = mock_agent

            extractor = FactExtractor()
            result = extractor.extract(
                summary="Long enough summary text. " * 20,
                research_topic="test",
            )

            assert len(result) == 10

    def test_extract_malformed_json_returns_empty(self):
        from agent.kb.extractor import FactExtractor

        with patch("agent.kb.extractor.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.step.return_value = "not a valid json response at all"
            mock_agent_cls.return_value = mock_agent

            extractor = FactExtractor()
            result = extractor.extract(
                summary="Long enough summary text with enough content. " * 10,
                research_topic="test",
            )

            assert result == []

    def test_extract_with_custom_model_id(self):
        from agent.kb.extractor import FactExtractor

        with patch("agent.kb.extractor.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.step.return_value = "```json\n[]\n```"
            mock_agent_cls.return_value = mock_agent

            extractor = FactExtractor(model_id="custom-model")
            extractor.extract(summary="Long enough summary text. " * 10, research_topic="test")

            mock_agent_cls.assert_called_once_with(model_id="custom-model")

    def test_validate_confidence_clamped(self):
        """Verify confidence is clamped to [0.0, 1.0]."""
        from agent.kb.extractor import FactExtractor

        facts = [
            {"fact": "negative conf", "source_url": "https://s.com", "confidence": -0.5},
            {"fact": "over 1 conf", "source_url": "https://s.com", "confidence": 2.5},
            {"fact": "valid conf", "source_url": "https://s.com", "confidence": 0.75},
        ]

        validated = FactExtractor._validate(facts)
        assert validated[0]["confidence"] == 0.0
        assert validated[1]["confidence"] == 1.0
        assert validated[2]["confidence"] == 0.75
