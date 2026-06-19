import os

from loguru import logger
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

from agent.exceptions import (
    LLMAuthError,
    LLMBadRequestError,
    LLMNetworkError,
    LLMRateLimitError,
    LLMServerError,
    LLMUnexpectedError,
)

_USAGE_TOTALS = {
    "calls": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "prompt_chars": 0,
}


def reset_usage_totals() -> None:
    """Reset process-local LLM usage counters for benchmark runs."""
    for key in _USAGE_TOTALS:
        _USAGE_TOTALS[key] = 0


def get_usage_totals() -> dict:
    """Return a copy of process-local LLM usage counters."""
    return dict(_USAGE_TOTALS)


def _record_usage(response, prompt: str) -> None:
    """Record token usage when the provider returns it."""
    _USAGE_TOTALS["calls"] += 1
    _USAGE_TOTALS["prompt_chars"] += len(prompt or "")

    usage = getattr(response, "usage", None)
    if not usage:
        return

    for source_attr, target_key in (
        ("prompt_tokens", "prompt_tokens"),
        ("completion_tokens", "completion_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        value = getattr(usage, source_attr, None)
        if value is not None:
            _USAGE_TOTALS[target_key] += int(value)


def _resolve_credentials(model_id: str) -> tuple[str | None, str | None]:
    """Resolve model-specific credentials with legacy env compatibility."""
    research_model = os.getenv("RESEARCH_LLM_MODEL")
    reasoning_model = os.getenv("REASONING_LLM_MODEL")

    if model_id == reasoning_model:
        return (
            os.getenv("REASONING_LLM_API_KEY"),
            os.getenv("REASONING_LLM_BASE_URL"),
        )
    if model_id == research_model:
        return (
            os.getenv("RESEARCH_LLM_API_KEY"),
            os.getenv("RESEARCH_LLM_BASE_URL"),
        )

    legacy_key = os.getenv("APP_TOKEN")
    legacy_url = os.getenv("LLM_BASE_URL")
    if legacy_key and legacy_url:
        return legacy_key, legacy_url

    return (
        os.getenv("RESEARCH_LLM_API_KEY") or os.getenv("REASONING_LLM_API_KEY"),
        os.getenv("RESEARCH_LLM_BASE_URL") or os.getenv("REASONING_LLM_BASE_URL"),
    )


def _translate_openai_error(exc: APIError) -> Exception:
    """将 OpenAI SDK 异常转换为 Agent 异常分类.

    映射规则：
      - 429 → LLMRateLimitError (Transient)
      - 5xx → LLMServerError (Transient)
      - 网络/超时 → LLMNetworkError (Transient)
      - 401 → LLMAuthError (Permanent)
      - 400/404 → LLMBadRequestError (Permanent)
      - 403 → LLMBadRequestError (Permanent)
    """
    # status_code 是 OpenAI SDK 异常的 property，部分子类（如 APIConnectionError）
    # 没有 response 属性，status_code 访问可能失败，需要安全读取
    try:
        status_code = exc.status_code
    except Exception:
        status_code = None

    if isinstance(exc, RateLimitError) or status_code == 429:
        return LLMRateLimitError(str(exc))
    if isinstance(exc, InternalServerError) or (status_code and status_code >= 500):
        return LLMServerError(str(exc))
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return LLMNetworkError(str(exc))
    if isinstance(exc, AuthenticationError) or status_code == 401:
        return LLMAuthError(str(exc))
    if isinstance(exc, PermissionDeniedError) or status_code == 403:
        return LLMBadRequestError(str(exc))
    if isinstance(exc, (BadRequestError, NotFoundError)) or status_code in (400, 404):
        return LLMBadRequestError(str(exc))

    # 未知 APIError — 保守归类为永久错误
    return LLMUnexpectedError(
        f"Unclassified OpenAI error (HTTP {status_code}): {exc}"
    )


class OpenAICompatibleLLM:

    def __init__(self, model_id=""):
        self.model_id = model_id

    def generate_response(self, query):
        api_key, base_url = _resolve_credentials(self.model_id)
        if not api_key or not base_url:
            raise LLMUnexpectedError(
                f"Missing LLM credentials for model '{self.model_id}'"
            )
        client = OpenAI(api_key=api_key, base_url=base_url)
        logger.debug(f"本次访问LLM模型为：{self.model_id}")

        try:
            response = client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {
                        "role": "user",
                        "content": query
                    }
                ],
                extra_body={"enable_thinking": False},
            )
        except APIError as e:
            raise _translate_openai_error(e) from e

        _record_usage(response, query)
        content = response.choices[0].message.content
        if content is None:
            raise LLMUnexpectedError("LLM returned empty content (None)")

        return content

    async def agenerate_response(self, query):
        """异步生成 LLM 响应——不阻塞事件循环."""
        api_key, base_url = _resolve_credentials(self.model_id)
        if not api_key or not base_url:
            raise LLMUnexpectedError(
                f"Missing LLM credentials for model '{self.model_id}'"
            )
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)

        try:
            response = await client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {
                        "role": "user",
                        "content": query
                    }
                ],
                extra_body={"enable_thinking": False},
            )
        except APIError as e:
            raise _translate_openai_error(e) from e

        _record_usage(response, query)
        content = response.choices[0].message.content
        if content is None:
            raise LLMUnexpectedError("LLM returned empty content (None)")

        return content
