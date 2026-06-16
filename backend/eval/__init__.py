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
    test_set.json — sample evaluation topics
"""
