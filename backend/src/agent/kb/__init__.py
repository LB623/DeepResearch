"""Knowledge Base module — Milvus-backed fact storage and retrieval.

Components:
  - FactStore      (fact_store.py)  — Milvus client wrapper, insert + search
  - FactExtractor  (extractor.py)   — LLM-based fact extraction from summaries

Usage:
    from agent.kb import FactStore, FactExtractor

    store = FactStore()
    extractor = FactExtractor()

    facts = extractor.extract(summary_text, research_topic)
    store.add_facts(facts)
    known = store.query("AI芯片市场趋势", top_k=10)
"""

from agent.kb.fact_store import FactStore
from agent.kb.extractor import FactExtractor
from agent.kb.lifecycle import (
    CATEGORY_TTL,
    FRESHNESS_MAX_AGE,
    KBLifecycleMode,
    get_mode,
    should_decay,
    should_filter,
    should_tag,
    should_warn,
)

__all__ = [
    "FactStore",
    "FactExtractor",
    "KBLifecycleMode",
    "get_mode",
    "should_filter",
    "should_decay",
    "should_tag",
    "should_warn",
    "FRESHNESS_MAX_AGE",
    "CATEGORY_TTL",
]
