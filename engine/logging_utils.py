"""带 trace_id 的日志封装"""
from loguru import logger
import sys
from typing import Optional
from .config import config


# 配置 loguru
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{extra[trace_id]}</cyan> | <level>{message}</level>",
    level=config.LOG_LEVEL,
)


def get_logger(trace_id: Optional[str] = None):
    """获取带 trace_id 的 logger
    
    Args:
        trace_id: 链路追踪 ID
        
    Returns:
        绑定了 trace_id 的 logger 实例
    """
    return logger.bind(trace_id=trace_id or "N/A")


def sanitize_log_message(msg: str, max_length: int = 200) -> str:
    """对日志消息进行脱敏处理
    
    Args:
        msg: 原始消息
        max_length: 最大长度
        
    Returns:
        脱敏后的消息
    """
    if len(msg) > max_length:
        return msg[:max_length] + f"... (truncated, total length: {len(msg)})"
    return msg

