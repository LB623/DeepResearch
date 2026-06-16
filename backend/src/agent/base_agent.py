import os
import copy
import traceback
import time
import threading
import asyncio
from loguru import logger
from agent.llm.llm import OpenAICompatibleLLM
from dashscope import Application
from agent.post import Post
import json
from agent.search_cache import get_cached, set_cached
from agent.exceptions import (
    TransientError,
    PermanentError,
    MCPRateLimitError,
    MCPAuthError,
    MCPAccessDeniedError,
    MCPParseError,
    MCPEmptyResultError,
    MCPServerError,
)


def _get_mcp_api_key() -> str | None:
    """Resolve the web-search key across current and legacy env names."""
    return (
        os.getenv("MCP_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("APP_TOKEN")
        or os.getenv("RESEARCH_LLM_API_KEY")
    )


class RateLimiter:
    """
    简单的令牌桶速率限制器
    用于控制API请求频率，避免触发429错误
    """
    def __init__(self, max_qps: float = 15.0):
        """
        初始化速率限制器

        Args:
            max_qps: 最大每秒请求数，默认15 QPS
        """
        self.max_qps = max_qps
        self.min_interval = 1.0 / max_qps  # 最小请求间隔（秒）
        self.last_request_time = 0
        self.lock = threading.Lock()
        self._alock = asyncio.Lock()  # async variant
        logger.info(f"速率限制器已初始化: 最大QPS={max_qps}, 最小间隔={self.min_interval:.3f}秒")

    def acquire(self):
        """
        获取请求许可，如果频率超限则等待

        Returns:
            float: 实际等待的时间（秒）
        """
        with self.lock:
            current_time = time.time()
            time_since_last = current_time - self.last_request_time

            if time_since_last < self.min_interval:
                wait_time = self.min_interval - time_since_last
                logger.debug(f"速率限制：需要等待 {wait_time:.3f} 秒")
                time.sleep(wait_time)
                self.last_request_time = time.time()
                return wait_time
            else:
                self.last_request_time = current_time
                return 0.0

    async def aacquire(self):
        """异步获取请求许可——不阻塞事件循环."""
        async with self._alock:
            current_time = time.time()
            time_since_last = current_time - self.last_request_time

            if time_since_last < self.min_interval:
                wait_time = self.min_interval - time_since_last
                logger.debug(f"速率限制(异步)：需要等待 {wait_time:.3f} 秒")
                await asyncio.sleep(wait_time)
                self.last_request_time = time.time()
                return wait_time
            else:
                self.last_request_time = current_time
                return 0.0


# 全局速率限制器实例（单例模式）
_web_search_rate_limiter = None

def get_web_search_rate_limiter(max_qps: float = None) -> RateLimiter:
    """
    获取全局Web搜索速率限制器实例

    Args:
        max_qps: 最大QPS，如果为None则从环境变量读取或使用默认值

    Returns:
        RateLimiter: 速率限制器实例
    """
    global _web_search_rate_limiter

    if _web_search_rate_limiter is None:
        if max_qps is None:
            # 从环境变量读取，默认为12 QPS（留有余量）
            max_qps = float(os.getenv("WEB_SEARCH_MAX_QPS", "12"))
        _web_search_rate_limiter = RateLimiter(max_qps=max_qps)

    return _web_search_rate_limiter


# ── 重试辅助函数 ──────────────────────────────────────────────────────────

def _retry_with_classified_errors(
    callable_fn,
    max_attempts: int = 3,
    base_delay: float = 1.5,
    error_prefix: str = "调用",
):
    """对可恢复错误重试，对不可恢复错误快速失败.

    Args:
        callable_fn: 无参数的可调用对象
        max_attempts: 最大尝试次数
        base_delay: 每次重试的基础等待时间（指数增长）
        error_prefix: 日志中的错误描述前缀

    Returns:
        callable_fn 的返回值，重试耗尽时返回 None

    Raises:
        PermanentError: 遇到不可恢复错误时直接抛出
    """

    for attempt in range(max_attempts):
        try:
            return callable_fn()
        except PermanentError:
            # 不可恢复错误 — 不重试，直接向上传播
            raise
        except TransientError as e:
            if attempt < max_attempts - 1:
                delay = base_delay * (attempt + 1)
                logger.warning(
                    f"{error_prefix}瞬时错误（尝试 {attempt + 1}/{max_attempts}），"
                    f"{delay:.1f}s 后重试：{e}"
                )
                time.sleep(delay)
            else:
                logger.error(
                    f"{error_prefix}重试{max_attempts}次全部失败：{e}"
                )
        except Exception as e:
            # 未知异常 — 保守处理：记录详细日志后重试
            if attempt < max_attempts - 1:
                delay = base_delay * (attempt + 1)
                logger.warning(
                    f"{error_prefix}未知错误（尝试 {attempt + 1}/{max_attempts}），"
                    f"{delay:.1f}s 后重试：{e}\n{traceback.format_exc()}"
                )
                time.sleep(delay)
            else:
                logger.error(
                    f"{error_prefix}重试{max_attempts}次全部失败（未知错误）：{e}\n"
                    f"{traceback.format_exc()}"
                )

    # 所有重试耗尽 — 返回 None 而非抛异常，保持向后兼容
    return None


class Agent:
    step_prompt = """{prompt}"""
    def __init__(self, model_id="deepseek-v4-flash"):
        self.llm = OpenAICompatibleLLM(model_id=model_id)

    def __call__(self, prompt):
        response = self.llm.generate_response(prompt)
        return response

    async def acall(self, prompt):
        """异步调用 LLM."""
        return await self.llm.agenerate_response(prompt)

    def set_step_prompt(self, prompt):
        self.step_prompt = prompt

    def step(self, **kwargs):
        step_prompt = self.prompt_format(self.step_prompt, **kwargs)

        def _attempt():
            response = self(step_prompt)
            return self.post_process(response)

        return _retry_with_classified_errors(
            _attempt,
            error_prefix="大模型调用",
        ) or ""

    async def astep(self, **kwargs):
        """异步执行 Agent step——不阻塞事件循环."""
        step_prompt = self.prompt_format(self.step_prompt, **kwargs)
        for attempt in range(3):
            try:
                response = await self.acall(step_prompt)
                response = self.post_process(response)
                return response
            except PermanentError as e:
                logger.error(
                    f"大模型调用永久错误，放弃重试：{e}\n"
                    f"错误类型: {type(e).__name__}"
                )
                raise
            except TransientError as e:
                if attempt < 2:
                    delay = 1.5 * (attempt + 1)
                    logger.warning(
                        f"大模型瞬时错误（尝试 {attempt + 1}/3），"
                        f"{delay:.1f}s 后重试：{e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"大模型调用重试3次全部失败：{e}\n"
                        f"错误类型: {type(e).__name__}"
                    )
            except Exception as e:
                if attempt < 2:
                    delay = 1.5 * (attempt + 1)
                    logger.warning(
                        f"大模型调用未知错误（尝试 {attempt + 1}/3），"
                        f"{delay:.1f}s 后重试：{e}\n{traceback.format_exc()}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"大模型调用重试3次全部失败（未知错误）：{e}\n"
                        f"错误类型: {type(e).__name__}\n"
                        f"{traceback.format_exc()}"
                    )
        return ""

    def post_process(self, response):
        return response

    def prompt_format(self, prompt, **kwargs):
        prompt_ = copy.deepcopy(prompt)
        for k in kwargs.keys():
            rep = "{"+k+"}"
            prompt_ = prompt_.replace(rep, str(kwargs[k]))
        return prompt_


class JsonAgent(Agent):
    def __init__(self, model_id="deepseek-v4-flash", keys=None):
        super().__init__(model_id)
        self.keys = keys

    def post_process(self, response):
        result = json.loads(Post.extract_pattern(response, pattern="json"))
        if not self.keys:
            return result
        return self.keys(**result)


class MCPAgent(Agent):

    def step(self, **kwargs):
        try:
            step_prompt = self.step_prompt.format(**kwargs)
        except (KeyError, ValueError) as e:
            logger.warning(f"MCP prompt格式化失败（缺少参数 {e}），使用原始prompt")
            step_prompt = self.step_prompt

        def _attempt():
            response = Application.call(
                api_key=_get_mcp_api_key(),
                app_id=os.getenv("MCP_APP_ID"),
                prompt=step_prompt,
                biz_params=kwargs,
            )
            result = self.post_process(response)
            if result is None:
                raise MCPEmptyResultError("MCP返回结果不正确（None）")
            return result

        return _retry_with_classified_errors(
            _attempt,
            base_delay=2.0,
            error_prefix="MCP调用",
        )

    async def astep(self, **kwargs):
        """异步 MCP 调用——dashscope 同步 API 通过 to_thread 包裹."""
        try:
            step_prompt = self.step_prompt.format(**kwargs)
        except (KeyError, ValueError) as e:
            logger.warning(f"MCP prompt格式化失败（缺少参数 {e}），使用原始prompt")
            step_prompt = self.step_prompt

        for attempt in range(3):
            try:
                response = await asyncio.to_thread(
                    Application.call,
                    api_key=_get_mcp_api_key(),
                    app_id=os.getenv("MCP_APP_ID"),
                    prompt=step_prompt,
                    biz_params=kwargs,
                )
                response = self.post_process(response)
                if response is None:
                    raise MCPEmptyResultError("MCP返回结果不正确（None）")
                return response
            except PermanentError:
                raise
            except TransientError as e:
                if attempt < 2:
                    delay = 2.0 * (attempt + 1)
                    logger.warning(
                        f"MCP瞬时错误（尝试 {attempt + 1}/3），"
                        f"{delay:.1f}s 后重试：{e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"MCP调用重试3次全部失败：{e}\n"
                        f"错误类型: {type(e).__name__}"
                    )
            except Exception as e:
                if attempt < 2:
                    delay = 2.0 * (attempt + 1)
                    logger.warning(
                        f"MCP调用未知错误（尝试 {attempt + 1}/3），"
                        f"{delay:.1f}s 后重试：{e}\n{traceback.format_exc()}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"MCP调用重试3次全部失败（未知错误）：{e}\n"
                        f"{traceback.format_exc()}"
                    )
        return None

    def post_process(self, response):
        if response.status_code == 200:
            response = json.loads(response.output.text)
            return response
        else:
            logger.error(f"MCP调用失败，HTTP状态码: {response.status_code}，响应: {response}")
            return None


class WebSearchAgent(MCPAgent):
    def step(self, prompt, **kwargs):
        try:
            step_prompt = self.step_prompt.format(prompt=prompt)
        except (KeyError, ValueError) as e:
            logger.warning(f"WebSearch prompt格式化失败（缺少参数 {e}），使用原始prompt")
            step_prompt = self.step_prompt

        count = kwargs.get("count", 10)

        # ── cache lookup ──────────────────────────────────────────
        cached = get_cached(prompt, count=count)
        if cached is not None:
            return cached

        api_key = _get_mcp_api_key()
        app_id = os.getenv("MCP_APP_ID")

        # 获取速率限制器
        rate_limiter = get_web_search_rate_limiter()

        def _attempt():
            # 在发送请求前进行速率限制检查
            wait_time = rate_limiter.acquire()
            if wait_time > 0:
                logger.debug(f"速率限制等待: {wait_time:.3f}秒")

            response = Application.call(
                api_key=api_key,
                app_id=app_id,
                prompt=step_prompt,
                biz_params=kwargs,
            )
            result = self.post_process(response)

            # ── cache store ────────────────────────────────────
            if result:
                set_cached(prompt, count=count, result=result)

            return result

        return _retry_with_classified_errors(
            _attempt,
            base_delay=2.0,
            error_prefix="Web搜索",
        )

    async def astep(self, prompt, **kwargs):
        """异步 Web 搜索——asyncio.to_thread 包裹同步 MCP API."""
        try:
            step_prompt = self.step_prompt.format(prompt=prompt)
        except (KeyError, ValueError) as e:
            logger.warning(f"WebSearch prompt格式化失败（缺少参数 {e}），使用原始prompt")
            step_prompt = self.step_prompt

        count = kwargs.get("count", 10)

        # ── cache lookup ──────────────────────────────────────────
        cached = get_cached(prompt, count=count)
        if cached is not None:
            return cached

        api_key = _get_mcp_api_key()
        app_id = os.getenv("MCP_APP_ID")
        rate_limiter = get_web_search_rate_limiter()

        for attempt in range(3):
            try:
                wait_time = await rate_limiter.aacquire()
                if wait_time > 0:
                    logger.debug(f"速率限制等待(异步): {wait_time:.3f}秒")

                response = await asyncio.to_thread(
                    Application.call,
                    api_key=api_key,
                    app_id=app_id,
                    prompt=step_prompt,
                    biz_params=kwargs,
                )
                response = self.post_process(response)

                if response:
                    set_cached(prompt, count=count, result=response)

                return response
            except PermanentError as e:
                logger.error(
                    f"Web搜索永久错误，放弃重试：{e}\n"
                    f"错误类型: {type(e).__name__}, 请求ID: {getattr(e, 'request_id', 'N/A')}"
                )
                raise
            except TransientError as e:
                if attempt < 2:
                    is_429 = "429" in str(e).lower() or isinstance(e, MCPRateLimitError)
                    delay = 5 * (attempt + 1) if is_429 else 2.0 * (attempt + 1)
                    logger.warning(
                        f"Web搜索瞬时错误（尝试 {attempt + 1}/3），"
                        f"{delay:.1f}s 后重试：{e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Web搜索重试3次全部失败：{e}\n"
                        f"错误类型: {type(e).__name__}"
                    )
            except Exception as e:
                error_msg = str(e)
                if attempt < 2:
                    if "429" in error_msg:
                        delay = 5 * (attempt + 1)
                    else:
                        delay = 2.0 * (attempt + 1)
                    logger.warning(
                        f"Web搜索未知错误（尝试 {attempt + 1}/3），"
                        f"{delay:.1f}s 后重试：{e}\n{traceback.format_exc()}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Web搜索重试3次全部失败（未知错误）：{e}\n"
                        f"错误类型: {type(e).__name__}\n"
                        f"{traceback.format_exc()}"
                    )
        return None

    def post_process(self, response):
        if response is None:
            raise MCPEmptyResultError("Web搜索结果不正确（response为None）")
        if response.status_code == 200:
            try:
                # 解析第一层JSON
                first_level = json.loads(response.output.text)

                # 检查API是否返回错误
                if "result" in first_level and first_level["result"].get("isError"):
                    error_content = first_level["result"]["content"][0]["text"] if "content" in first_level["result"] else "未知错误"
                    try:
                        error_detail = json.loads(error_content)
                        status = error_detail.get("status", "unknown")
                        request_id = error_detail.get("request_id", "unknown")

                        if status == 429:
                            logger.error(f"API速率限制(429)，请求ID: {request_id}。建议增加请求间隔或联系API提供商提高配额")
                            raise MCPRateLimitError(
                                f"API请求频率超限(429)，请稍后重试",
                                request_id=request_id,
                            )
                        elif status == 401:
                            logger.error(f"API认证失败(401)，请求ID: {request_id}")
                            raise MCPAuthError(
                                f"API认证失败，请检查APP_TOKEN配置",
                                request_id=request_id,
                            )
                        elif status == 403:
                            logger.error(f"API访问被拒绝(403)，请求ID: {request_id}")
                            raise MCPAccessDeniedError(
                                f"API访问被拒绝，请检查权限配置",
                                request_id=request_id,
                            )
                        else:
                            logger.error(f"API返回错误状态 {status}，请求ID: {request_id}，详情: {error_detail}")
                            raise MCPServerError(
                                f"API返回错误(状态码: {status})",
                                request_id=request_id,
                            )
                    except json.JSONDecodeError:
                        logger.error(f"API返回错误，但无法解析错误详情: {error_content}")
                        raise MCPParseError(f"API调用失败: {error_content}")

                # 尝试不同的路径获取pages数据
                pages = None

                # 路径1: result.content[0].text -> pages
                if "result" in first_level and "content" in first_level["result"]:
                    content_text = first_level["result"]["content"][0]["text"]
                    second_level = json.loads(content_text)
                    if "pages" in second_level:
                        pages = second_level["pages"]

                # 路径2: 直接在第一层查找pages
                elif "pages" in first_level:
                    pages = first_level["pages"]

                # 路径3: 查找data.pages
                elif "data" in first_level and "pages" in first_level["data"]:
                    pages = first_level["data"]["pages"]

                if pages is None:
                    logger.error(f"无法从响应中提取pages数据，响应结构: {json.dumps(first_level, ensure_ascii=False)[:500]}")
                    raise MCPParseError("无法从Web搜索结果中提取页面数据")

                # 确保pages是列表
                if not isinstance(pages, list):
                    logger.error(f"pages不是列表类型: {type(pages)}")
                    raise MCPParseError("Web搜索结果格式错误")

                # 提取需要的字段
                processed_pages = []
                for page in pages:
                    if isinstance(page, dict):
                        processed_pages.append({
                            "snippet": page.get("snippet", ""),
                            "title": page.get("title", ""),
                            "url": page.get("url", "")
                        })

                return processed_pages
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析失败: {e}, 原始响应: {response.output.text[:500]}")
                raise MCPParseError(f"Web搜索结果JSON解析失败: {str(e)}") from e
            except (KeyError, IndexError, TypeError) as e:
                logger.error(f"数据结构解析失败: {e}, 响应内容: {response.output.text[:500]}")
                raise MCPParseError(f"Web搜索结果数据结构错误: {str(e)}") from e
        else:
            logger.error(f"MCP调用失败，HTTP状态码: {response.status_code}，响应: {response}")
            raise MCPServerError(f"Web搜索API调用失败(HTTP {response.status_code})")


if __name__ == '__main__':
    agent = WebSearchAgent()
    response = agent.step(prompt="稳定币", count=10)
    logger.info(response)
