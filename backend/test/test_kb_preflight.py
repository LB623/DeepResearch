"""Public readiness command contract for Milvus and Embedding."""

import os


def test_kb_preflight_returns_nonzero_when_embedding_is_unavailable(capsys):
    from agent.kb.preflight import main

    class UnreadyStore:
        def readiness(self):
            return {
                "milvus_ready": True,
                "embedding_ready": False,
                "embedding_model": "bge-m3",
                "embedding_dim": 1024,
                "error_type": "RuntimeError",
            }

    exit_code = main(store_factory=UnreadyStore)

    assert exit_code == 1
    assert '"embedding_ready": false' in capsys.readouterr().out


def test_kb_preflight_loads_dotenv_before_constructing_store(
    tmp_path,
    monkeypatch,
):
    from agent.kb.preflight import main

    (tmp_path / ".env").write_text(
        "EMBEDDING_MODEL=dotenv-model\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)

    class EnvAwareStore:
        def __init__(self):
            self.model = os.getenv("EMBEDDING_MODEL")

        def readiness(self):
            return {
                "milvus_ready": True,
                "embedding_ready": self.model == "dotenv-model",
            }

    assert main(store_factory=EnvAwareStore) == 0
