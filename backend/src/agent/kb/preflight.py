"""CLI readiness probe for the Milvus and Embedding boundary."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable

from dotenv import load_dotenv

from agent.kb.fact_store import FactStore


def main(store_factory: Callable[[], FactStore] = FactStore) -> int:
    load_dotenv(dotenv_path=".env")
    try:
        readiness = store_factory().readiness()
    except Exception as exc:
        readiness = {
            "milvus_ready": False,
            "embedding_ready": False,
            "error_type": type(exc).__name__,
        }

    print(json.dumps(readiness, ensure_ascii=False, sort_keys=True))
    return 0 if (
        readiness.get("milvus_ready")
        and readiness.get("embedding_ready")
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
