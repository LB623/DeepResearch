import json
import os
import re
import time
import traceback
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from agent.configuration import load_available_models_from_env
from agent.logger import log_request_details, setup_logger

# Define the FastAPI app
app = FastAPI(docs_url=None, redoc_url=None)
setup_logger()

_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,128}")


def _enabled(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "on"})


def _request_id_from_header(value: str | None) -> str:
    if value and _REQUEST_ID_RE.fullmatch(value):
        return value
    return str(uuid.uuid4())


def _model_list_error() -> JSONResponse:
    return JSONResponse(
        content={
            "error": {
                "code": "MODEL_LIST_UNAVAILABLE",
                "message": "模型列表暂时不可用",
            }
        },
        status_code=500,
    )


# 添加获取模型列表的API端点
@app.get("/api/models")
async def get_available_models():
    """获取可用的LLM模型列表"""
    try:
        # 直接从环境变量加载模型列表
        models = load_available_models_from_env()
        models_data = [
            {
                "model_id": model.model_id,
                "display_name": model.display_name,
                "icon": model.icon,
                "icon_color": model.icon_color
            }
            for model in models
        ]
        logger.info(f"返回模型列表: {models_data}")
        return JSONResponse(content={"models": models_data})
    except ValueError as e:
        # 配置解析错误（如 AVAILABLE_MODELS JSON 格式错误）
        logger.error("模型配置解析失败 (ValueError): {}", e)
        return _model_list_error()
    except Exception as e:
        # 未知异常 — 记录完整 traceback 用于排查
        logger.error("获取模型列表失败 ({}): {}", type(e).__name__, e)
        logger.error(traceback.format_exc())
        return _model_list_error()

# 添加请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = _request_id_from_header(request.headers.get("X-Request-ID"))
    started_at = time.perf_counter()
    logger.info(
        "HTTP request started method={} path={} request_id={}",
        request.method,
        request.url.path,
        request_id,
    )

    try:
        if (
            _enabled(os.getenv("LOG_REQUEST_BODY"))
            and request.method in {"POST", "PUT", "PATCH"}
        ):
            body = await request.body()
            if body:
                try:
                    body_data = json.loads(body.decode())
                    log_request_details(body_data)
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    logger.debug(
                        "无法解析请求体为JSON ({}), length={}",
                        type(e).__name__,
                        len(body),
                    )
    except Exception as e:
        # 日志记录本身的错误不应影响请求处理
        logger.error(
            "记录请求日志时出错 ({}) request_id={}: {}\n{}",
            type(e).__name__,
            request_id,
            e,
            traceback.format_exc(),
        )

    try:
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started_at) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "HTTP request completed method={} path={} status={} duration_ms={:.1f} "
            "request_id={}",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response
    except Exception as e:
        logger.error(
            "HTTP request failed method={} path={} request_id={} error_type={}\n{}",
            request.method,
            request.url.path,
            request_id,
            type(e).__name__,
            traceback.format_exc(),
        )
        raise
