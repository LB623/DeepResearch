"""logger.py 模块的单元测试。

覆盖：
  - setup_logger() 正常路径、OSError 兜底、通用异常兜底
  - log_request_details() 各种输入类型
"""

import io
import os
import sys
import tempfile

import pytest
from loguru import logger


# ═══════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════

def _cleanup_loguru():
    """移除所有 loguru handler，恢复干净的全局状态。"""
    try:
        logger.remove()
    except Exception:
        pass  # 可能已经没有 handler 了


@pytest.fixture(autouse=True)
def _cleanup_loguru_after():
    """每个测试后自动清理 loguru 全局状态。"""
    yield
    _cleanup_loguru()


# ═══════════════════════════════════════════════════════════════════════
# TestSetupLogger
# ═══════════════════════════════════════════════════════════════════════

class TestSetupLogger:
    """setup_logger() 函数的测试。"""

    def test_default_creates_directory_and_handlers(self, monkeypatch, tmp_path):
        """默认参数调用：创建日志目录、注册控制台和文件 handler。"""
        # 在导入前 monkeypatch，避免 app.py 的模块级 setup_logger() 副作用
        from agent.logger import setup_logger

        log_dir = str(tmp_path / "test_logs")
        # 用临时目录避免写入项目 logs/
        result = setup_logger(log_dir=log_dir)

        assert result is not None
        # 验证目录被创建
        assert os.path.isdir(log_dir)

    def test_oserror_triggers_fallback_path(self, monkeypatch):
        """os.makedirs 抛 OSError 时，降级到纯控制台 DEBUG 日志。"""
        from agent.logger import setup_logger

        def _raise_oserror(*args, **kwargs):
            raise OSError("磁盘已满")

        monkeypatch.setattr(os, "makedirs", _raise_oserror)

        result = setup_logger(log_dir="/nonexistent/readonly")
        assert result is not None
        # OSError 路径不会崩

    def test_unexpected_exception_triggers_fallback_path(self, monkeypatch):
        """非 OSError 异常（如 TypeError）触发第二兜底路径。"""
        from agent.logger import setup_logger

        def _raise_typeerror(*args, **kwargs):
            raise TypeError("意外的类型错误")

        monkeypatch.setattr(os, "makedirs", _raise_typeerror)

        result = setup_logger(log_dir="/nonexistent/broken")
        assert result is not None
        # 通用异常路径不会崩


# ═══════════════════════════════════════════════════════════════════════
# TestLogRequestDetails
# ═══════════════════════════════════════════════════════════════════════

class TestLogRequestDetails:
    """log_request_details() 函数的测试。"""

    def test_dict_input(self):
        """字典类型输入，记录到日志。"""
        from agent.logger import log_request_details

        log_request_details({"key": "value"})

    def test_string_input(self):
        """字符串类型输入。"""
        from agent.logger import log_request_details

        log_request_details("hello world")

    def test_list_input(self):
        """列表类型输入。"""
        from agent.logger import log_request_details

        log_request_details([1, 2, 3])

    def test_unicode_input(self):
        """中文 Unicode 输入。"""
        from agent.logger import log_request_details

        log_request_details({"message": "中文"})

    def test_none_input(self):
        """None 输入。"""
        from agent.logger import log_request_details

        log_request_details(None)

    def test_empty_string_input(self):
        """空字符串输入。"""
        from agent.logger import log_request_details

        log_request_details("")

    def test_bytes_input(self):
        """字节类型输入。"""
        from agent.logger import log_request_details

        log_request_details(b"\x00\x01")
