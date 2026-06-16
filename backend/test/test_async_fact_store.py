"""Async FactStore tests — validates _aembed() async wrapper."""

import pytest
from unittest.mock import MagicMock, patch


class TestAsyncFactStore:
    @pytest.mark.asyncio
    async def test_aembed_calls_sync_embed(self):
        """_aembed wraps _embed via asyncio.to_thread."""
        from agent.kb.fact_store import FactStore

        with patch("agent.kb.fact_store.MilvusClient") as mock_client_cls, \
             patch("agent.kb.fact_store.requests.post") as mock_post:
            mock_client = MagicMock()
            mock_client.has_collection.return_value = True
            mock_client_cls.return_value = mock_client

            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {
                "data": [{"embedding": [0.1] * 1024, "index": 0}]
            }
            mock_post.return_value = mock_resp

            store = FactStore()
            result = await store._aembed(["test text"])

            assert result is not None
            assert len(result) == 1
            assert len(result[0]) == 1024
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_aembed_propagates_errors(self):
        """Errors from _embed should propagate through _aembed."""
        from agent.kb.fact_store import FactStore
        from agent.exceptions import KBEmbeddingFatalError

        with patch("agent.kb.fact_store.MilvusClient") as mock_client_cls, \
             patch("agent.kb.fact_store.requests.post") as mock_post, \
             patch("agent.kb.fact_store.time.sleep"):
            mock_client = MagicMock()
            mock_client.has_collection.return_value = True
            mock_client_cls.return_value = mock_client

            import requests as req
            fail_resp = MagicMock()
            fail_resp.status_code = 401
            http_err = req.HTTPError("401 Unauthorized")
            http_err.response = fail_resp
            mock_post.side_effect = http_err

            store = FactStore()
            with pytest.raises(KBEmbeddingFatalError, match="401"):
                await store._aembed(["test"])
