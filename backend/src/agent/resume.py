"""Small helpers for resuming checkpointed DeepResearch tasks."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

from agent.checkpoint import make_thread_config
from agent.graph import graph


def get_task_snapshot(thread_id: str):
    """Return the latest checkpoint snapshot for a task."""
    return graph.get_state(make_thread_config(thread_id))


async def resume_task(
    thread_id: str,
    user_message: str | None = None,
    **configurable: Any,
) -> dict:
    """Resume a task by stable ``thread_id``.

    With ``user_message=None`` LangGraph resumes from the last pending node.
    Passing a message appends user input onto the checkpointed state and starts
    a new graph step from that state.
    """
    config = make_thread_config(thread_id, **configurable)
    graph_input = (
        None
        if user_message is None
        else {"messages": [HumanMessage(content=user_message)]}
    )
    return await graph.ainvoke(graph_input, config=config)
