# DeepResearch Agent Guide

## Project map

- `backend/src/agent/graph.py`: main LangGraph orchestration.
- `backend/src/agent/sub_agents/`: research and writer subgraphs.
- `backend/src/agent/kb/`: Milvus fact memory and reconnecting provider.
- `backend/src/agent/checkpoint.py`: durable Redis checkpoint policy.
- `backend/test/`: backend unit and graph behavior tests.
- `frontend/src/`: React application and colocated Vitest tests.
- `docs/plans/`: accepted engineering designs and test seams.

## Boundaries

- Redis Checkpoint is durable task state. With `CHECKPOINT_BACKEND=redis`,
  connection failure must fail closed unless
  `CHECKPOINT_FALLBACK_TO_MEMORY=1` is explicitly set for local development.
- Redis Search Cache is an optimization and may fall back to process memory.
- Milvus failure must not stop research; `FactStoreProvider` retries after its
  cooldown instead of permanently disabling knowledge storage.
- Request bodies, prompts, messages, credentials, and internal exceptions must
  not enter default logs or client error responses.
- Per-task search/token/time/no-progress counters live in LangGraph state so
  checkpoint resume does not reset budgets.

## Verification

Run the non-mutating delivery gate from the repository root:

```bash
make verify
```

Backend dependencies are locked in `backend/uv.lock`. Update the lock
intentionally after changing `backend/pyproject.toml`; CI rejects stale locks.
The frontend build enforces a main JavaScript chunk below 500 KB.

Commands under `backend/eval/` may call paid LLM, Web Search, Milvus, and
embedding services. Do not run them as part of routine verification unless the
user explicitly requests an external evaluation.

Do not modify or commit the user-generated `output/` and `tmp/` directories.
