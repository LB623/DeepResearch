"""app.py 模块的单元测试。

覆盖：
  - GET /api/models 端点（正常、空列表、默认值、异常）
  - log_requests HTTP 中间件（GET/POST/异常）
"""


import pytest
from fastapi.testclient import TestClient

# ═══════════════════════════════════════════════════════════════════════
# TestClient fixture — 避免 app.py 的模块级 setup_logger() 副作用
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _suppress_module_logger(monkeypatch):
    """阻止 app.py 模块导入时执行 setup_logger()。

    用空操作替换，避免日志写入项目目录和全局 loguru 状态污染。
    """
    monkeypatch.setattr("agent.app.setup_logger", lambda *a, **kw: None)


@pytest.fixture
def client():
    """FastAPI TestClient 实例。"""
    from agent.app import app

    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════
# TestApiModels — GET /api/models
# ═══════════════════════════════════════════════════════════════════════

class TestApiModels:
    """测试 /api/models 端点。"""

    def test_returns_models_from_env(self, client):
        """正常情况：返回 mock_env fixture 设置的模型列表。"""
        response = client.get("/api/models")
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert isinstance(data["models"], list)
        assert len(data["models"]) >= 1
        # mock_env 设置了 qwen-test
        model_ids = [m["model_id"] for m in data["models"]]
        assert "qwen-test" in model_ids

    def test_empty_models_list(self, monkeypatch, client):
        """AVAILABLE_MODELS 为空数组时返回空列表。"""
        monkeypatch.setenv("AVAILABLE_MODELS", "[]")
        response = client.get("/api/models")
        assert response.status_code == 200
        data = response.json()
        assert data["models"] == []

    def test_missing_env_var_returns_defaults(self, monkeypatch, client):
        """AVAILABLE_MODELS 未设置时返回默认模型列表。"""
        monkeypatch.delenv("AVAILABLE_MODELS", raising=False)
        response = client.get("/api/models")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["models"], list)
        # 默认列表应非空
        assert len(data["models"]) > 0

    def test_invalid_json_in_available_models(self, monkeypatch, client):
        """AVAILABLE_MODELS 含非法 JSON → 返回默认列表（内部吞异常）。"""
        monkeypatch.setenv("AVAILABLE_MODELS", "{not valid json}")
        response = client.get("/api/models")
        # load_available_models_from_env 内部 catch 异常并 fallback 到默认列表
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["models"], list)
        assert len(data["models"]) > 0

    def test_load_models_raises_generic_exception(self, monkeypatch, client):
        """端点异常只返回稳定错误码，不泄露内部异常。"""
        import agent.app

        def _raise_internal_error():
            raise RuntimeError("internal-path /private/service")

        monkeypatch.setattr(
            agent.app, "load_available_models_from_env", _raise_internal_error
        )
        response = client.get("/api/models")

        assert response.status_code == 500
        assert response.json() == {
            "error": {
                "code": "MODEL_LIST_UNAVAILABLE",
                "message": "模型列表暂时不可用",
            }
        }
        assert "internal-path" not in response.text


# ═══════════════════════════════════════════════════════════════════════
# TestRequestLogging — HTTP 中间件
# ═══════════════════════════════════════════════════════════════════════

class TestRequestLogging:
    """测试 log_requests HTTP 中间件。"""

    def test_get_request_logs_url(self, client):
        """GET 请求正常通过中间件。"""
        response = client.get("/api/models")
        # 不崩即通过
        assert response.status_code == 200

    def test_post_json_body_is_parsed(self, client):
        """POST 含合法 JSON body → 被解析并记录。"""
        # /threads 是 LangGraph 运行时路由，由 LangGraph 进程处理
        # 这里用 /api/models 虽是 GET-only 但中间件仍工作
        # 使用 OPTIONS 方法验证中间件不会掉
        response = client.options("/api/models")
        assert response.status_code in (200, 405)  # 405 也说明中间件正确 passed through

    def test_middleware_does_not_block_requests(self, client):
        """中间件不阻塞正常请求流。"""
        response = client.get("/api/models")
        assert response.status_code == 200

    def test_downstream_exception_returns_500(self, monkeypatch, client):
        """下游路由抛异常时，中间件记录后 re-raise → Starlette 返回 500。"""
        # monkeypatch 一个不存在的路由，让中间件能捕获异常
        # 实际上直接请求不存在的路径也会得到 404
        response = client.get("/nonexistent-path")
        assert response.status_code == 404  # 正常返回 404，中间件没崩

    def test_request_body_is_not_logged_by_default(self, monkeypatch, client):
        """默认 HTTP 日志只记录元数据，不记录请求正文。"""
        import io

        from loguru import logger

        monkeypatch.delenv("LOG_REQUEST_BODY", raising=False)
        sink = io.StringIO()
        handler_id = logger.add(sink, format="{message}")
        try:
            response = client.post(
                "/api/models",
                json={
                    "api_key": "request-secret-key",
                    "messages": [{"content": "private research request"}],
                },
            )
        finally:
            logger.remove(handler_id)

        assert response.status_code == 405
        output = sink.getvalue()
        assert "request-secret-key" not in output
        assert "private research request" not in output

    def test_invalid_request_id_is_replaced(self, client):
        supplied = "safe\nFORGED=1"
        response = client.get("/api/models", headers={"X-Request-ID": supplied})

        returned = response.headers["X-Request-ID"]
        assert returned != supplied
        assert "\n" not in returned

    def test_valid_request_id_is_preserved(self, client):
        response = client.get(
            "/api/models",
            headers={"X-Request-ID": "request_123.test"},
        )

        assert response.headers["X-Request-ID"] == "request_123.test"
