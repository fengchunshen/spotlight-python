"""全局配置模块"""
import os
from typing import Optional


class Config:
    """全局配置类"""
    
    # 日志级别
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # 是否在日志中输出详细的 trace 信息
    LOG_TRACE_ENABLED: bool = os.getenv("LOG_TRACE_ENABLED", "true").lower() == "true"
    
    # SSE 保活间隔（秒）
    SSE_KEEPALIVE_INTERVAL: int = int(os.getenv("SSE_KEEPALIVE_INTERVAL", "30"))
    
    # HTTP 工具默认超时时间（秒）
    HTTP_TOOL_TIMEOUT: int = int(os.getenv("HTTP_TOOL_TIMEOUT", "30"))


config = Config()

