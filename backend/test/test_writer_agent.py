"""Integration tests for WriterAgent sub-graph — nodes, routing, and debate loop."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.state import OverallState
from agent.sub_agents.writer_agent import (
    writer_agent_graph,
    _outline,
    _draft,
    _critic_review,
    _route_after_critic,
    _cite_and_polish,
    _OUTLINE,
    _DRAFT,
    _CRITIC_REVIEW,
    _CITE_AND_POLISH,
)


# ═══════════════════════════════════════════════════════════════════════
# Graph topology
# ═══════════════════════════════════════════════════════════════════════

class TestWriterAgentGraphTopology:
    def test_graph_is_compiled(self):
        assert writer_agent_graph is not None
        assert hasattr(writer_agent_graph, "nodes")

    def test_required_nodes_exist(self):
        nodes = list(writer_agent_graph.nodes.keys())
        assert _OUTLINE in nodes
        assert _DRAFT in nodes
        assert _CRITIC_REVIEW in nodes
        assert _CITE_AND_POLISH in nodes


# ═══════════════════════════════════════════════════════════════════════
# _outline node (async)
# ═══════════════════════════════════════════════════════════════════════

class TestOutline:
    @pytest.mark.asyncio
    async def test_generates_outline(self, sample_state):
        with patch("agent.sub_agents.writer_agent.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(
                return_value="```markdown\n# 报告大纲\n\n## 第一章\n## 第二章\n```"
            )
            mock_agent_cls.return_value = mock_agent

            result = await _outline(sample_state, {"configurable": {}})

            assert "report_outline" in result
            assert "第一章" in result["report_outline"]
            assert result["revision_count"] == 0
            assert result["max_revisions"] == 3


# ═══════════════════════════════════════════════════════════════════════
# _draft node (async)
# ═══════════════════════════════════════════════════════════════════════

class TestDraft:
    @pytest.mark.asyncio
    async def test_first_draft_from_scratch(self, sample_state):
        with patch("agent.sub_agents.writer_agent.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(
                return_value="```markdown\n# 报告正文\n\n这是草稿内容\n```"
            )
            mock_agent_cls.return_value = mock_agent

            result = await _draft(sample_state, {"configurable": {}})

            assert "report_draft" in result
            assert "报告正文" in result["report_draft"]
            assert result.get("revision_count", 0) == 0

    @pytest.mark.asyncio
    async def test_revision_with_feedback(self, sample_state):
        state = {
            **sample_state,
            "critic_feedback": "## 审稿评分: 5/10\n## 具体问题:\n- 数据源需要更新",
            "report_outline": "# Outline\nTest",
            "revision_count": 1,
        }

        with patch("agent.sub_agents.writer_agent.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(
                return_value="```markdown\n# 修订后的报告\n\n已修改\n```"
            )
            mock_agent_cls.return_value = mock_agent

            result = await _draft(state, {"configurable": {}})

            assert "report_draft" in result
            assert result["revision_count"] == 2
            assert result["critic_feedback"] == ""


# ═══════════════════════════════════════════════════════════════════════
# _critic_review node (async)
# ═══════════════════════════════════════════════════════════════════════

class TestCriticReview:
    @pytest.mark.asyncio
    async def test_review_with_issues(self, sample_state):
        from agent.tools_and_schemas import CritiqueResult, Issue

        state = {
            **sample_state,
            "report_draft": "# Draft content\n\nSome analysis here.",
        }

        with patch("agent.sub_agents.writer_agent.JsonAgent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(return_value=CritiqueResult(
                overall_rating=6.5,
                issues=[
                    Issue(
                        severity="critical",
                        location="第1章",
                        problem="数据源链接失效",
                        suggestion="更新为最新链接",
                    ),
                    Issue(
                        severity="minor",
                        location="第3章",
                        problem="措辞不够专业",
                        suggestion="使用更正式的表述",
                    ),
                ],
                ready_for_polish=False,
                summary="需要小修",
            ))
            mock_agent_cls.return_value = mock_agent

            result = await _critic_review(state, {"configurable": {}})

            assert result["critic_score"] == 6.5
            assert "critic_feedback" in result
            assert "审稿评分: 6.5/10" in result["critic_feedback"]
            assert "CRITICAL" in result["critic_feedback"]
            assert "MINOR" in result["critic_feedback"]

    @pytest.mark.asyncio
    async def test_review_no_issues(self, sample_state):
        from agent.tools_and_schemas import CritiqueResult

        state = {**sample_state, "report_draft": "# Perfect draft"}

        with patch("agent.sub_agents.writer_agent.JsonAgent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(return_value=CritiqueResult(
                overall_rating=9.0,
                issues=[],
                ready_for_polish=True,
                summary="优秀，可直接发布",
            ))
            mock_agent_cls.return_value = mock_agent

            result = await _critic_review(state, {"configurable": {}})

            assert result["critic_score"] == 9.0
            assert "无明显问题" in result["critic_feedback"]


# ═══════════════════════════════════════════════════════════════════════
# _route_after_critic routing (sync — pure routing)
# ═══════════════════════════════════════════════════════════════════════

class TestRouteAfterCritic:
    def test_max_revisions_force_polish(self, sample_state):
        state = {**sample_state, "revision_count": 3, "max_revisions": 3, "critic_score": 4.0}
        result = _route_after_critic(state, {"configurable": {}})
        assert result == _CITE_AND_POLISH

    def test_excellent_score_goes_to_polish(self, sample_state):
        # 路由只看 ready_for_polish 和 revision_count，不看 critic_score
        state = {**sample_state, "revision_count": 0, "max_revisions": 3, "ready_for_polish": True}
        result = _route_after_critic(state, {"configurable": {}})
        assert result == _CITE_AND_POLISH

    def test_good_score_after_revision_goes_to_polish(self, sample_state):
        # 同上：路由只看 ready_for_polish 和 revision_count
        state = {**sample_state, "revision_count": 1, "max_revisions": 3, "ready_for_polish": True}
        result = _route_after_critic(state, {"configurable": {}})
        assert result == _CITE_AND_POLISH

    def test_low_score_needs_revision(self, sample_state):
        state = {**sample_state, "revision_count": 0, "max_revisions": 3, "critic_score": 4.0}
        result = _route_after_critic(state, {"configurable": {}})
        assert result == _DRAFT

    def test_moderate_score_first_pass_needs_revision(self, sample_state):
        state = {**sample_state, "revision_count": 0, "max_revisions": 3, "critic_score": 6.5}
        result = _route_after_critic(state, {"configurable": {}})
        assert result == _DRAFT


# ═══════════════════════════════════════════════════════════════════════
# _cite_and_polish node (async)
# ═══════════════════════════════════════════════════════════════════════

class TestCiteAndPolish:
    @pytest.mark.asyncio
    async def test_polish_and_replace_urls(self, sample_state):
        state = {
            **sample_state,
            "report_draft": "# Report\n\nSee [source](https://search.com/id/0-0) for details.",
        }

        with patch("agent.sub_agents.writer_agent.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(
                return_value="```markdown\n# Report\n\nSee [source](https://search.com/id/0-0) for details.\n```"
            )
            mock_agent_cls.return_value = mock_agent

            result = await _cite_and_polish(state, {"configurable": {}})

            assert "messages" in result
            final_content = result["messages"][0].content
            assert "https://real.com/1" in final_content
            assert "https://search.com/id/0-0" not in final_content

    @pytest.mark.asyncio
    async def test_polish_deduplicates_sources(self, sample_state):
        draft_with_one_citation = "# Report\n\nSee [ref](https://search.com/id/0-0)."

        state = {
            **sample_state,
            "report_draft": draft_with_one_citation,
        }

        with patch("agent.sub_agents.writer_agent.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(
                return_value="```markdown\n" + draft_with_one_citation + "\n```"
            )
            mock_agent_cls.return_value = mock_agent

            result = await _cite_and_polish(state, {"configurable": {}})

            assert len(result["sources_gathered"]) == 1
            assert result["sources_gathered"][0]["short_url"] == "https://search.com/id/0-0"


# ═══════════════════════════════════════════════════════════════════════
# TestCiteAndPolishEdgeCases — URL 替换边界覆盖
# ═══════════════════════════════════════════════════════════════════════

class TestCiteAndPolishEdgeCases:
    """测试 _cite_and_polish 的 URL 替换边界场景。"""

    @pytest.mark.asyncio
    async def test_empty_sources_gathered_does_not_crash(self, sample_state):
        """sources_gathered 为空时，不崩且不替换任何内容。"""
        state = {
            **sample_state,
            "sources_gathered": [],
            "report_draft": "# Report\n\nNo sources here.",
        }

        with patch("agent.sub_agents.writer_agent.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(
                return_value="```markdown\n# Report\n\nNo sources here.\n```"
            )
            mock_agent_cls.return_value = mock_agent

            result = await _cite_and_polish(state, {"configurable": {}})

            assert "messages" in result
            assert result["sources_gathered"] == []

    @pytest.mark.asyncio
    async def test_duplicate_urls_are_deduplicated(self, sample_state):
        """来源中有重复 URL → 去重后只保留各自的出现。

        注意：_cite_and_polish 按 short_url 匹配，不按 value 去重。
        两个不同 short_url 即使指向同一个 value，都会出现在最终结果中。
        """
        state = {
            **sample_state,
            "report_draft": "# Report\n\nSee [A](https://search.com/id/0-0) and [B](https://search.com/id/0-1).",
            "sources_gathered": [
                {"short_url": "https://search.com/id/0-0", "value": "https://same.com", "label": "A"},
                {"short_url": "https://search.com/id/0-1", "value": "https://same.com", "label": "B"},
            ],
        }

        with patch("agent.sub_agents.writer_agent.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(
                return_value="```markdown\n# Report\n\nSee [A](https://search.com/id/0-0) and [B](https://search.com/id/0-1).\n```"
            )
            mock_agent_cls.return_value = mock_agent

            result = await _cite_and_polish(state, {"configurable": {}})

            # 两个 short_url 都在 draft 中出现 → 各被保留一条
            assert len(result["sources_gathered"]) == 2

    @pytest.mark.asyncio
    async def test_short_url_not_in_draft_excluded(self, sample_state):
        """短链接不在原文中 → 该来源不出现在最终列表。"""
        state = {
            **sample_state,
            "report_draft": "# Report\n\nSee [source](https://search.com/id/0-0).",
            "sources_gathered": [
                {"short_url": "https://search.com/id/0-0", "value": "https://real.com/1", "label": "Source 1"},
                {"short_url": "https://search.com/id/0-1", "value": "https://real.com/2", "label": "Source 2"},
            ],
        }

        with patch("agent.sub_agents.writer_agent.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(
                return_value="```markdown\n# Report\n\nSee [source](https://search.com/id/0-0).\n```"
            )
            mock_agent_cls.return_value = mock_agent

            result = await _cite_and_polish(state, {"configurable": {}})

            # https://search.com/id/0-1 不在 draft 中，应被排除
            gathered = result["sources_gathered"]
            short_urls = [s["short_url"] for s in gathered]
            assert "https://search.com/id/0-0" in short_urls
            assert "https://search.com/id/0-1" not in short_urls

    @pytest.mark.asyncio
    async def test_repeated_short_url_replaced_all_occurrences(self, sample_state):
        """短链接在原文中出现多次 → 每处都被替换为真实 URL。"""
        state = {
            **sample_state,
            "report_draft": (
                "# Report\n\n"
                "First mention [here](https://search.com/id/0-0). "
                "Second mention [also here](https://search.com/id/0-0)."
            ),
        }

        with patch("agent.sub_agents.writer_agent.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(
                return_value=(
                    "```markdown\n"
                    "# Report\n\n"
                    "First mention [here](https://search.com/id/0-0). "
                    "Second mention [also here](https://search.com/id/0-0).\n"
                    "```"
                )
            )
            mock_agent_cls.return_value = mock_agent

            result = await _cite_and_polish(state, {"configurable": {}})

            final_content = result["messages"][0].content
            # 短链接已被替换
            assert "https://search.com/id/0-0" not in final_content
            # 真实 URL 出现了
            assert "https://real.com/1" in final_content
