"""Tests for Pydantic schemas used in agent state and tool outputs."""

import pytest
from pydantic import ValidationError
from agent.tools_and_schemas import (
    SearchQueryList,
    Reflection,
    PlanReflection,
    Issue,
    CritiqueResult,
)


class TestSearchQueryList:
    def test_valid(self):
        obj = SearchQueryList(
            query=["AI芯片市场规模", "NVIDIA市场份额"],
            rationale="需要了解市场规模和竞争格局",
        )
        assert len(obj.query) == 2
        assert "市场规模" in obj.rationale

    def test_empty_query_list(self):
        obj = SearchQueryList(query=[], rationale="no queries needed")
        assert obj.query == []

    def test_missing_query_raises(self):
        with pytest.raises(ValidationError):
            SearchQueryList(rationale="missing query field")


class TestReflection:
    def test_valid_sufficient(self):
        obj = Reflection(
            is_sufficient=True,
            knowledge_gap="",
            follow_up_queries=[],
        )
        assert obj.is_sufficient is True
        assert obj.follow_up_queries == []

    def test_valid_insufficient(self):
        obj = Reflection(
            is_sufficient=False,
            knowledge_gap="缺少竞争对手分析数据",
            follow_up_queries=["AI芯片竞争对手", "AMD市场份额"],
        )
        assert obj.is_sufficient is False
        assert len(obj.follow_up_queries) == 2

    def test_missing_fields_raises(self):
        with pytest.raises(ValidationError):
            Reflection(is_sufficient=True)


class TestPlanReflection:
    def test_satisfied(self):
        obj = PlanReflection(satisfy=True)
        assert obj.satisfy is True

    def test_not_satisfied(self):
        obj = PlanReflection(satisfy=False)
        assert obj.satisfy is False


class TestIssue:
    def test_valid_issue(self):
        iss = Issue(
            severity="critical",
            location="第2.1节",
            problem="数据源链接失效",
            suggestion="更新为2025年最新报告链接",
        )
        assert iss.severity == "critical"
        assert "2.1" in iss.location

    def test_different_severities(self):
        for sev in ["critical", "major", "minor"]:
            iss = Issue(severity=sev, location="test", problem="p", suggestion="s")
            assert iss.severity == sev

    def test_missing_fields_raises(self):
        with pytest.raises(ValidationError):
            Issue(severity="major", location="x")  # missing problem, suggestion


class TestCritiqueResult:
    def test_excellent_draft(self):
        result = CritiqueResult(
            overall_rating=9.0,
            issues=[],
            ready_for_polish=True,
            summary="报告质量优秀，可以直接发布",
        )
        assert result.overall_rating == 9.0
        assert result.ready_for_polish is True
        assert len(result.issues) == 0

    def test_needs_revision(self):
        result = CritiqueResult(
            overall_rating=5.5,
            issues=[
                Issue(
                    severity="critical",
                    location="第3章",
                    problem="事实错误",
                    suggestion="核实数据来源",
                ),
                Issue(
                    severity="major",
                    location="第1章",
                    problem="论证不足",
                    suggestion="补充案例支持",
                ),
            ],
            ready_for_polish=False,
            summary="需要大幅修改",
        )
        assert result.overall_rating == 5.5
        assert len(result.issues) == 2
        assert result.ready_for_polish is False

    def test_rating_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            CritiqueResult(
                overall_rating=11.0,  # > 10
                issues=[],
                ready_for_polish=False,
                summary="invalid",
            )

    def test_negative_rating_raises(self):
        with pytest.raises(ValidationError):
            CritiqueResult(
                overall_rating=-1.0,
                issues=[],
                ready_for_polish=False,
                summary="invalid",
            )
