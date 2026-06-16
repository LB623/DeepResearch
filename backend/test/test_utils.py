"""Tests for utility functions: resolve_urls, get_research_topic, etc."""

import pytest
from langchain_core.messages import HumanMessage, AIMessage
from agent.utils import resolve_urls, get_research_topic, get_last_user_response


class TestResolveUrls:
    def test_normal_case(self):
        urls = [
            {"url": "https://very-long-url.com/page/1"},
            {"url": "https://very-long-url.com/page/2"},
        ]
        result = resolve_urls(urls, id=5)
        assert len(result) == 2
        assert result["https://very-long-url.com/page/1"] == "https://search.com/id/5-0"
        assert result["https://very-long-url.com/page/2"] == "https://search.com/id/5-1"

    def test_duplicate_urls_get_same_short_url(self):
        urls = [
            {"url": "https://example.com/a"},
            {"url": "https://example.com/a"},
            {"url": "https://example.com/b"},
        ]
        result = resolve_urls(urls, id=1)
        assert len(result) == 2
        assert result["https://example.com/a"] == "https://search.com/id/1-0"
        assert result["https://example.com/b"] == "https://search.com/id/1-2"

    def test_none_input(self):
        result = resolve_urls(None, id=1)
        assert result == {}

    def test_empty_list(self):
        result = resolve_urls([], id=1)
        assert result == {}

    def test_non_list_input(self):
        result = resolve_urls("not a list", id=1)
        assert result == {}

    def test_missing_url_key(self):
        urls = [{"title": "no url here"}, {"url": "https://example.com"}]
        result = resolve_urls(urls, id=1)
        assert len(result) == 1
        assert "https://example.com" in result

    def test_different_ids_produce_different_prefixes(self):
        urls = [{"url": "https://example.com"}]
        r1 = resolve_urls(urls, id=3)
        r2 = resolve_urls(urls, id=7)
        assert r1["https://example.com"] == "https://search.com/id/3-0"
        assert r2["https://example.com"] == "https://search.com/id/7-0"


class TestGetResearchTopic:
    def test_single_message(self):
        messages = [HumanMessage(content="AI芯片市场分析")]
        result = get_research_topic(messages)
        assert result == "AI芯片市场分析"

    def test_multiple_messages_concatenated(self):
        messages = [
            HumanMessage(content="分析AI芯片"),
            AIMessage(content="好的，我来帮你分析"),
            HumanMessage(content="重点关注NVIDIA"),
        ]
        result = get_research_topic(messages)
        assert "User: 分析AI芯片" in result
        assert "Assistant: 好的，我来帮你分析" in result
        assert "User: 重点关注NVIDIA" in result

    def test_ignore_contexts_excludes_ai_messages(self):
        messages = [
            HumanMessage(content="topic"),
            AIMessage(content="should be ignored"),
        ]
        result = get_research_topic(messages, ignore_contexts=["should be ignored"])
        assert "should be ignored" not in result


class TestGetLastUserResponse:
    def test_returns_last_user_message(self):
        messages = [
            HumanMessage(content="first question"),
            AIMessage(content="answer"),
            HumanMessage(content="follow up"),
        ]
        result = get_last_user_response(messages)
        assert "follow up" in result

    def test_no_user_messages(self):
        messages = [AIMessage(content="only AI")]
        result = get_last_user_response(messages)
        assert result == ""

    def test_single_user_message(self):
        messages = [HumanMessage(content="hello")]
        result = get_last_user_response(messages)
        assert "hello" in result
