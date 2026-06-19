"""Integration tests for WriterAgent sub-graph — nodes, routing, and debate loop."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.sub_agents.writer_agent import (
    _CITE_AND_POLISH,
    _CRITIC_REVIEW,
    _DRAFT,
    _OUTLINE,
    _cite_and_polish,
    _critic_review,
    _draft,
    _draft_rejection_reason,
    _outline,
    _polish_rejection_reason,
    _route_after_critic,
    _unsupported_named_terms,
    writer_agent_graph,
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
            assert (
                mock_agent.astep.await_args.kwargs["previous_draft"]
                == state["report_draft"]
            )

    @pytest.mark.asyncio
    async def test_incomplete_draft_retries_against_outline(self, sample_state):
        state = {
            **sample_state,
            "report_outline": "## 1. Overview\n## 2. Risks\n## 3. Conclusion",
        }
        partial = "```markdown\n## 1. Overview\n\nOnly the first section.\n```"
        complete = (
            "```markdown\n## 1. Overview\n\nText.\n\n"
            "## 2. Risks\n\nRisks.\n\n## 3. Conclusion\n\nDone.\n```"
        )

        with patch("agent.sub_agents.writer_agent.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(side_effect=[partial, complete])
            mock_agent_cls.return_value = mock_agent

            result = await _draft(state, {"configurable": {}})

            assert mock_agent.astep.await_count == 2
            assert "## 3. Conclusion" in result["report_draft"]
            assert mock_agent.astep.await_args.kwargs["previous_draft"].startswith(
                "## 1. Overview"
            )


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
            mock_agent.astep = AsyncMock(
                return_value=CritiqueResult(
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
                )
            )
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
            mock_agent.astep = AsyncMock(
                return_value=CritiqueResult(
                    overall_rating=9.0,
                    issues=[],
                    ready_for_polish=True,
                    summary="优秀，可直接发布",
                )
            )
            mock_agent_cls.return_value = mock_agent

            result = await _critic_review(state, {"configurable": {}})

            assert result["critic_score"] == 9.0
            assert "无明显问题" in result["critic_feedback"]

    @pytest.mark.asyncio
    async def test_critic_uses_reflection_model(self, sample_state):
        from agent.tools_and_schemas import CritiqueResult

        state = {**sample_state, "report_draft": "# Draft"}
        state.pop("reasoning_model", None)

        with patch("agent.sub_agents.writer_agent.JsonAgent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(
                return_value=CritiqueResult(
                    overall_rating=9.0,
                    issues=[],
                    ready_for_polish=True,
                    summary="ready",
                )
            )
            mock_agent_cls.return_value = mock_agent

            await _critic_review(
                state,
                {
                    "configurable": {
                        "reflection_model": "critic-pro",
                        "answer_model": "writer-flash",
                    }
                },
            )

            mock_agent_cls.assert_called_once_with(
                model_id="critic-pro", keys=CritiqueResult
            )

    @pytest.mark.asyncio
    async def test_critic_receives_unsupported_named_term_audit(self, sample_state):
        from agent.tools_and_schemas import CritiqueResult

        state = {
            **sample_state,
            "report_draft": "# Draft\n\nKiro 与 Tessl 可用于该流程。",
        }

        with patch("agent.sub_agents.writer_agent.JsonAgent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(
                return_value=CritiqueResult(
                    overall_rating=4.0,
                    issues=[],
                    ready_for_polish=False,
                    summary="unsupported tools",
                )
            )
            mock_agent_cls.return_value = mock_agent

            await _critic_review(state, {"configurable": {}})

            audit = mock_agent.astep.await_args.kwargs["unsupported_named_terms"]
            assert "Kiro" in audit
            assert "Tessl" in audit


# ═══════════════════════════════════════════════════════════════════════
# _route_after_critic routing (sync — pure routing)
# ═══════════════════════════════════════════════════════════════════════


class TestRouteAfterCritic:
    def test_max_revisions_force_polish(self, sample_state):
        state = {
            **sample_state,
            "revision_count": 3,
            "max_revisions": 3,
            "critic_score": 4.0,
        }
        result = _route_after_critic(state, {"configurable": {}})
        assert result == _CITE_AND_POLISH

    def test_excellent_score_goes_to_polish(self, sample_state):
        # 路由只看 ready_for_polish 和 revision_count，不看 critic_score
        state = {
            **sample_state,
            "revision_count": 0,
            "max_revisions": 3,
            "ready_for_polish": True,
        }
        result = _route_after_critic(state, {"configurable": {}})
        assert result == _CITE_AND_POLISH

    def test_good_score_after_revision_goes_to_polish(self, sample_state):
        # 同上：路由只看 ready_for_polish 和 revision_count
        state = {
            **sample_state,
            "revision_count": 1,
            "max_revisions": 3,
            "ready_for_polish": True,
        }
        result = _route_after_critic(state, {"configurable": {}})
        assert result == _CITE_AND_POLISH

    def test_low_score_needs_revision(self, sample_state):
        state = {
            **sample_state,
            "revision_count": 0,
            "max_revisions": 3,
            "critic_score": 4.0,
        }
        result = _route_after_critic(state, {"configurable": {}})
        assert result == _DRAFT

    def test_moderate_score_first_pass_needs_revision(self, sample_state):
        state = {
            **sample_state,
            "revision_count": 0,
            "max_revisions": 3,
            "critic_score": 6.5,
        }
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
            assert (
                result["sources_gathered"][0]["short_url"]
                == "https://search.com/id/0-0"
            )

    @pytest.mark.asyncio
    async def test_truncated_polish_falls_back_to_complete_draft(self, sample_state):
        draft = (
            "# Report\n\n"
            "## 1. Overview\n\n" + "完整内容。" * 220 + "\n\n"
            "## 2. Risks\n\n风险分析。\n\n"
            "## 3. Conclusion\n\n结论。"
        )
        state = {**sample_state, "report_draft": draft}

        with patch("agent.sub_agents.writer_agent.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(
                return_value="```markdown\n# Report\n\n## 1. Overview\n\n截断内容"
            )
            mock_agent_cls.return_value = mock_agent

            result = await _cite_and_polish(state, {"configurable": {}})

            assert result["messages"][0].content == draft
            assert mock_agent.astep.await_args.kwargs["critic_feedback"] == ""

    @pytest.mark.asyncio
    async def test_polish_with_unknown_url_falls_back_to_draft(self, sample_state):
        draft = "# Report\n\nSee [source](https://search.com/id/0-0)."
        state = {**sample_state, "report_draft": draft}

        with patch("agent.sub_agents.writer_agent.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(
                return_value=(
                    "```markdown\n# Report\n\n"
                    "See [invented](https://invented.example.com/report).\n```"
                )
            )
            mock_agent_cls.return_value = mock_agent

            result = await _cite_and_polish(state, {"configurable": {}})

            final_content = result["messages"][0].content
            assert "https://invented.example.com" not in final_content
            assert "https://real.com/1" in final_content

    @pytest.mark.asyncio
    async def test_material_citation_tokens_become_markdown_links(self, sample_state):
        """模型输出裸材料标签时，后端应兜底转成可点击 Markdown 链接。"""
        state = {
            **sample_state,
            "report_draft": "# Report\n\n结论需要引用材料。",
            "sources_gathered": [
                {
                    "short_url": "https://search.com/id/0-0",
                    "value": "https://real.com/1",
                    "label": "Source 1",
                },
                {
                    "short_url": "https://search.com/id/0-1",
                    "value": "https://real.com/2",
                    "label": "Source 2",
                },
                {
                    "short_url": "https://search.com/id/0-2",
                    "value": "https://real.com/3",
                    "label": "Source 3",
                },
            ],
        }

        with patch("agent.sub_agents.writer_agent.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(
                return_value="```markdown\n# Report\n\n关键发现来自[材料-00][材料-02]。\n```"
            )
            mock_agent_cls.return_value = mock_agent

            result = await _cite_and_polish(state, {"configurable": {}})

            final_content = result["messages"][0].content
            assert "[材料-00](https://real.com/1)" in final_content
            assert "[材料-02](https://real.com/3)" in final_content
            assert "[材料-00][材料-02]" not in final_content
            assert len(result["sources_gathered"]) == 2

    @pytest.mark.asyncio
    async def test_material_citation_markdown_link_not_double_wrapped(
        self, sample_state
    ):
        """已经带 URL 的材料引用不应被改成嵌套链接。"""
        state = {
            **sample_state,
            "report_draft": "# Report\n\n结论需要引用材料。",
        }

        with patch("agent.sub_agents.writer_agent.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(
                return_value=(
                    "```markdown\n"
                    "# Report\n\n"
                    "关键发现来自[材料-00](https://real.com/1)。\n"
                    "```"
                )
            )
            mock_agent_cls.return_value = mock_agent

            result = await _cite_and_polish(state, {"configurable": {}})

            final_content = result["messages"][0].content
            assert "[材料-00](https://real.com/1)" in final_content
            assert "](" in final_content
            assert "https://real.com/1](https://real.com/1)" not in final_content

    @pytest.mark.asyncio
    async def test_internal_citation_variants_become_source_links(self, sample_state):
        state = {
            **sample_state,
            "report_draft": "# Report\n\n结论。",
            "sources_gathered": [
                {
                    "short_url": "https://search.com/id/0-0",
                    "value": "https://real.com/1",
                    "label": "A",
                },
                {
                    "short_url": "https://search.com/id/1-1",
                    "value": "https://real.com/2",
                    "label": "B",
                },
                {
                    "short_url": "https://search.com/id/3-7",
                    "value": "https://real.com/3",
                    "label": "C",
                },
            ],
        }

        with patch("agent.sub_agents.writer_agent.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(
                return_value=(
                    "```markdown\n# Report\n\n"
                    "事实A[id/0-0]，事实B[[1-1]]，事实C[search.com/id/3-7]。\n```"
                )
            )
            mock_agent_cls.return_value = mock_agent

            result = await _cite_and_polish(state, {"configurable": {}})

            final_content = result["messages"][0].content
            assert "[0-0](https://real.com/1)" in final_content
            assert "[1-1](https://real.com/2)" in final_content
            assert "[3-7](https://real.com/3)" in final_content
            assert len(result["sources_gathered"]) == 3

    @pytest.mark.asyncio
    async def test_existing_real_url_is_retained_in_sources(self, sample_state):
        state = {
            **sample_state,
            "report_draft": "# Report\n\n结论。",
        }

        with patch("agent.sub_agents.writer_agent.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(
                return_value="```markdown\n# Report\n\n[A](https://real.com/1)。\n```"
            )
            mock_agent_cls.return_value = mock_agent

            result = await _cite_and_polish(state, {"configurable": {}})

            assert len(result["sources_gathered"]) == 1
            assert result["sources_gathered"][0]["value"] == "https://real.com/1"


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
                {
                    "short_url": "https://search.com/id/0-0",
                    "value": "https://same.com",
                    "label": "A",
                },
                {
                    "short_url": "https://search.com/id/0-1",
                    "value": "https://same.com",
                    "label": "B",
                },
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
                {
                    "short_url": "https://search.com/id/0-0",
                    "value": "https://real.com/1",
                    "label": "Source 1",
                },
                {
                    "short_url": "https://search.com/id/0-1",
                    "value": "https://real.com/2",
                    "label": "Source 2",
                },
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


class TestPolishCompletenessGuard:
    def test_accepts_complete_report(self, sample_state):
        draft = "# Report\n\n## 1. Overview\n\nText.\n\n## 2. Conclusion\n\nDone."
        polished = (
            "# Report\n\n## 1. Overview\n\nBetter text.\n\n## 2. Conclusion\n\nDone."
        )

        assert (
            _polish_rejection_reason(
                draft,
                polished,
                sample_state["sources_gathered"],
            )
            is None
        )

    def test_rejects_missing_heading(self, sample_state):
        draft = "# Report\n\n## 1. Overview\n\nText.\n\n## 2. Conclusion\n\nDone."
        polished = "# Report\n\n## 1. Overview\n\nText."

        reason = _polish_rejection_reason(
            draft,
            polished,
            sample_state["sources_gathered"],
        )

        assert reason is not None
        assert "missing report headings" in reason

    def test_draft_rejects_missing_outline_section(self):
        outline = "## 1. Overview\n## 2. Risks\n## 3. Conclusion"
        draft = "## 1. Overview\n\nText.\n\n## 2. Risks\n\nRisk."

        reason = _draft_rejection_reason(outline, draft)

        assert reason is not None
        assert "3. conclusion" in reason

    def test_unsupported_named_terms_are_compared_with_evidence(self):
        unsupported = _unsupported_named_terms(
            "Kiro、Tessl 与 GitHub 可用于该流程。",
            evidence="GitHub is supported.",
            research_topic="SDD 与 AGENTS.md",
        )

        assert unsupported == ["Kiro", "Tessl"]

    def test_polish_rejects_new_named_terms(self, sample_state):
        draft = "# Report\n\n## 1. Tools\n\n现有工具。"
        polished = "# Report\n\n## 1. Tools\n\n新增 Kiro 工具。"

        reason = _polish_rejection_reason(
            draft,
            polished,
            sample_state["sources_gathered"],
        )

        assert reason is not None
        assert "new named terms" in reason
