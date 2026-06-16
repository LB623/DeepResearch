"""Sub-Agent graphs that encapsulate independent phases of the research pipeline.

Each sub-agent is a self-contained LangGraph StateGraph with its own nodes and
routing logic.  Sub-agents are composed into the main orchestrator graph in
`agent.graph`.

Sub-agents:
  - ResearchAgent: query generation → parallel web search → critique loop
  - WriterAgent:   outline → draft sections → cite & polish
"""

from agent.sub_agents.research_agent import research_agent_graph
from agent.sub_agents.writer_agent import writer_agent_graph

__all__ = ["research_agent_graph", "writer_agent_graph"]
