import os
import sys
from loguru import logger
import atexit


def setup_logger(log_dir="logs", console_log_level="INFO", file_log_level="DEBUG"):
    """
    配置日志
    Args:
        log_dir: 日志目录
        console_log_level: 控制台日志级别
        file_log_level: 文件日志级别
    """
    try:

        # 确保日志目录存在
        os.makedirs(log_dir, exist_ok=True)
        
        # 移除默认处理器
        logger.remove()
        # 添加控制台处理器
        logger.add(
            sys.stderr,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <blue><level>{message}</level></blue>",
            level=console_log_level
        )
        logger.add(
            os.path.join(log_dir, "ZhiPoAI_DR_{time:YYYY-MM-DD}.log"),
            rotation="00:00",  # 每天轮换
            retention="30 days",  # 保留30天
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level=file_log_level,
            encoding="utf-8"  # 添加UTF-8编码支持，解决中文乱码问题
            # enqueue=True  启用异步日志记录，避免阻塞调用
        )
        
        # 注册程序退出时的处理函数，确保所有日志都被写入
        atexit.register(lambda: logger.complete() if hasattr(logger, 'complete') else None)
    except OSError as e:
        # 文件系统错误（权限不足、磁盘满等）— 降级到纯控制台日志
        logger.remove()
        logger.add(
            sys.stderr,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <red>日志配置错误: {message}</red>",
            level="DEBUG"
        )
        logger.error(f"日志目录创建失败 (OSError): {e}")
    except Exception as e:
        # 其他意外异常 — 降级到纯控制台日志并记录完整错误
        logger.remove()
        logger.add(
            sys.stderr,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <red>日志配置错误: {message}</red>",
            level="DEBUG"
        )
        logger.error(f"日志配置失败 ({type(e).__name__}): {e}")
    
    return logger


def log_request_details(request_data):
    """
    记录请求详细信息
    Args:
        request_data: 请求数据
    """
    logger.info(f"收到前端请求: {request_data}")


# def log_node_input_output(node_name, input_data=None, output_data=None):
#     """
#     记录节点输入输出
#     Args:
#         node_name: 节点名称
#         input_data: 输入数据
#         output_data: 输出数据
#     """
#     if input_data is not None:
#         logger.info(f"节点 [{node_name}] 已接收输入....")
#         logger.debug(f"节点 [{node_name}] 已接收输入: {input_data}")
#     if output_data is not None:
#         logger.debug(f"节点 [{node_name}] 输出: {output_data}")