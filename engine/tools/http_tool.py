"""通用 HTTP 插件执行器

支持从 vault 中注入认证信息
"""
from typing import Any, Dict
import httpx
from engine.schemas.payload import ToolConfig
from engine.logging_utils import get_logger
from engine.config import config


async def execute_http_tool(
    tool_cfg: ToolConfig, 
    args: Dict[str, Any], 
    vault: Dict[str, str],
    trace_id: str = ""
) -> Any:
    """执行 HTTP 工具调用
    
    Args:
        tool_cfg: 工具配置
        args: 工具参数
        vault: 密钥保险库
        trace_id: 链路追踪 ID
        
    Returns:
        HTTP 响应的 JSON 数据
        
    Raises:
        httpx.HTTPError: HTTP 请求失败
    """
    logger = get_logger(trace_id)
    exec_cfg = tool_cfg.execution_config
    
    url = exec_cfg.get("url")
    if not url:
        raise ValueError(f"Tool {tool_cfg.name} missing 'url' in execution_config")
    
    method = exec_cfg.get("method", "GET").upper()
    auth_cfg = exec_cfg.get("auth_config")
    
    # 构建请求头
    headers: Dict[str, str] = {}
    if auth_cfg:
        source_key = auth_cfg.get("source")
        target_header = auth_cfg.get("target")
        if source_key and target_header and source_key in vault:
            headers[target_header] = vault[source_key]
            logger.info(f"HTTP tool {tool_cfg.name}: injected auth header {target_header}")
    
    # 执行 HTTP 请求
    logger.info(f"HTTP tool {tool_cfg.name}: {method} {url}")
    
    async with httpx.AsyncClient(timeout=config.HTTP_TOOL_TIMEOUT) as client:
        if method == "GET":
            resp = await client.get(url, params=args, headers=headers)
        elif method == "POST":
            resp = await client.post(url, json=args, headers=headers)
        elif method == "PUT":
            resp = await client.put(url, json=args, headers=headers)
        elif method == "DELETE":
            resp = await client.delete(url, params=args, headers=headers)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
    
    resp.raise_for_status()
    
    try:
        result = resp.json()
        logger.info(f"HTTP tool {tool_cfg.name}: success")
        return result
    except Exception as e:
        logger.warning(f"HTTP tool {tool_cfg.name}: response is not JSON, returning text")
        return {"text": resp.text}

