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

    # 知识库工作目录
    KNOWLEDGE_WORK_DIR: str = os.getenv("KNOWLEDGE_WORK_DIR", "./saves/knowledge_base_data")

    # Milvus 配置
    MILVUS_URI: str = os.getenv("MILVUS_URI", "http://58.247.21.68:39530")
    MILVUS_TOKEN: str = os.getenv("MILVUS_TOKEN", "")
    MILVUS_DB: str = os.getenv("MILVUS_DB", "default")
    MILVUS_COLLECTION_PREFIX: str = os.getenv("MILVUS_COLLECTION_PREFIX", "kb_")

    # Java 上传接口配置
    FILE_UPLOAD_URL: str = os.getenv("FILE_UPLOAD_URL", "")
    FILE_UPLOAD_FIELD: str = os.getenv("FILE_UPLOAD_FIELD", "file")
    FILE_UPLOAD_HEADERS: str = os.getenv("FILE_UPLOAD_HEADERS", "")


config = Config()

