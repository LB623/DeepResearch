"""DeepResearch Agent evaluation framework.

Provides LLM-as-Judge scoring for both end-to-end report quality and
component-level node output quality (plan, queries, critique, citations).

Quick start:
    python -m eval.run_eval --mode e2e
    python -m eval.run_eval --mode comp --topic "你的研究课题"

Modules:
    prompts     — judge prompt templates for each evaluation dimension
    judge       — LLM judge wrapper + Pydantic scoring schemas
    evaluator   — orchestrates agent invocation and scoring
    run_eval    — CLI entry point
    dataset     — layered E2E fixed-set schema and loader
    aggregate   — offline mean/std/hallucination/A/B aggregation
    output_contract — deterministic citation/leftover/guard metrics
    run_groundedness — replay historical E2E reports, no paid APIs
    run_guard_eval — score the fixed Writer-guard corpus
    test_set_e2e.json — canonical layered E2E set (smoke 5 / core 30 / full 100)
    test_set.json — sample evaluation topics
"""
