"""Regression tests for evaluation harness state/config propagation."""

from langchain_core.messages import AIMessage

from eval.evaluator import Evaluator, TopicCfg


def test_evaluator_passes_topic_limits_into_research_state():
    evaluator = Evaluator()
    calls: list[tuple[dict, dict]] = []

    def fake_invoke(state: dict, config: dict) -> dict:
        calls.append((state, config))
        if len(calls) == 1:
            return {"plan": "# Plan", "plan_messages": []}
        return {
            "messages": [AIMessage(content="# Report\n\n" + "complete " * 30)],
            "sources_gathered": [],
        }

    evaluator._invoke_graph = fake_invoke
    cfg = TopicCfg(
        topic="fixed limits",
        initial_search_query_count=1,
        max_research_loops=1,
    )

    try:
        evaluator._invoke_agent_with_feedback(cfg)

        research_state = calls[1][0]
        assert research_state["initial_search_query_count"] == 1
        assert research_state["max_research_loops"] == 1
        assert research_state["research_loop_count"] == 0
    finally:
        evaluator.close()
