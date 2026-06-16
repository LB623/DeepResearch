"""Agent pipeline 异常分类体系.

将 LLM 调用、MCP 搜索、KB 操作中的异常分为两类：
  - TransientError: 可恢复的瞬时错误，应重试
  - PermanentError: 不可恢复的永久错误，应快速失败

Usage:
    from agent.exceptions import TransientError, PermanentError, ...

    try:
        response = llm.generate_response(prompt)
    except TransientError:
        logger.warning("瞬时错误，重试中...")
        # retry
    except PermanentError:
        logger.error("永久错误，放弃")
        raise
"""

from __future__ import annotations


# ═══════════════════════════════════════════════════════════════════════
# 基类
# ═══════════════════════════════════════════════════════════════════════

class AgentError(Exception):
    """Agent pipeline 所有异常的基类."""

    def __init__(self, message: str = "", *, request_id: str | None = None):
        super().__init__(message)
        self.request_id = request_id


class TransientError(AgentError):
    """可恢复的瞬时错误 — 调用方应重试.

    包括：网络超时、服务端 5xx、速率限制 429、连接中断.
    """


class PermanentError(AgentError):
    """不可恢复的永久错误 — 调用方不应重试.

    包括：认证失败 401、权限不足 403、参数错误 400、资源不存在 404.
    """


# ═══════════════════════════════════════════════════════════════════════
# LLM 调用异常
# ═══════════════════════════════════════════════════════════════════════

class LLMError(AgentError):
    """LLM 调用异常基类."""


class LLMRateLimitError(LLMError, TransientError):
    """LLM API 速率限制 (429)."""


class LLMServerError(LLMError, TransientError):
    """LLM 服务端错误 (5xx)."""


class LLMNetworkError(LLMError, TransientError):
    """LLM 网络超时 / 连接中断."""


class LLMAuthError(LLMError, PermanentError):
    """LLM API 认证失败 (401)."""


class LLMBadRequestError(LLMError, PermanentError):
    """LLM API 参数错误 (400) / 模型不存在 (404)."""


class LLMUnexpectedError(LLMError, PermanentError):
    """LLM 返回不符合预期的响应（如空内容、格式错误）."""


# ═══════════════════════════════════════════════════════════════════════
# MCP / Web 搜索异常
# ═══════════════════════════════════════════════════════════════════════

class MCPError(AgentError):
    """MCP 调用异常基类."""


class MCPRateLimitError(MCPError, TransientError):
    """MCP 搜索 API 速率限制 (429)."""


class MCPServerError(MCPError, TransientError):
    """MCP 搜索服务端错误."""


class MCPAuthError(MCPError, PermanentError):
    """MCP API 认证失败 (401)."""


class MCPAccessDeniedError(MCPError, PermanentError):
    """MCP API 访问被拒绝 (403)."""


class MCPParseError(MCPError, PermanentError):
    """MCP 响应解析失败 — 数据结构不符合预期."""


class MCPEmptyResultError(MCPError, TransientError):
    """MCP 返回空结果 — 可能是搜索关键词问题."""


# ═══════════════════════════════════════════════════════════════════════
# KB / Milvus 异常
# ═══════════════════════════════════════════════════════════════════════

class KBError(AgentError):
    """知识库操作异常基类."""


class KBConnectionError(KBError, TransientError):
    """Milvus 连接失败 / 超时."""


class KBEmbeddingError(KBError, TransientError):
    """Embedding API 调用瞬时失败 (429 / 5xx / 网络)."""


class KBEmbeddingFatalError(KBError, PermanentError):
    """Embedding API 不可恢复失败 (认证 / 参数错误)."""


class KBConfigError(KBError, PermanentError):
    """KB 配置错误（维度不匹配、集合不存在等）."""


# ═══════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════

def is_transient(exc: BaseException) -> bool:
    """判断异常是否为可恢复的瞬时错误."""
    if isinstance(exc, TransientError):
        return True
    # 兼容原生异常
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    return False


def is_permanent(exc: BaseException) -> bool:
    """判断异常是否为不可恢复的永久错误."""
    if isinstance(exc, PermanentError):
        return True
    return False
