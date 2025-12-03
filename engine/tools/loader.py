"""工具加载器 - 从 runtime_config.tools 动态加载工具"""
from typing import Dict, Any, List, Callable
from engine.schemas.payload import ToolConfig
from engine.tools.http_tool import execute_http_tool
from engine.logging_utils import get_logger


def build_tools_from_runtime(
    tool_cfgs: List[ToolConfig],
    vault: Dict[str, str],
    trace_id: str = ""
) -> Dict[str, Callable]:
    """根据 runtime_config.tools 构建运行时工具集合
    
    Args:
        tool_cfgs: 工具配置列表
        vault: 密钥保险库
        trace_id: 链路追踪 ID
        
    Returns:
        工具名 -> 可调用对象的字典
    """
    logger = get_logger(trace_id)
    tools: Dict[str, Callable] = {}

    for cfg in tool_cfgs:
        if cfg.type == "HTTP":
            # 为每个 HTTP 工具创建独立的闭包
            async def _http_runner(args: Dict[str, Any], _cfg=cfg, _vault=vault, _tid=trace_id):
                return await execute_http_tool(_cfg, args, _vault, _tid)
            
            tools[cfg.name] = _http_runner
            logger.info(f"已加载 HTTP 工具: {cfg.name}")

        elif cfg.type == "NATIVE":
            # TODO: 通过 execution_config["class"] 反射加载 BaseNativeTool 子类
            async def _not_impl(args: Dict[str, Any], _cfg=cfg):
                raise NotImplementedError(f"NATIVE tool {_cfg.name} not implemented yet")
            
            tools[cfg.name] = _not_impl
            logger.warning(f"NATIVE 工具 {cfg.name} 已注册但尚未实现")
        
        else:
            logger.warning(f"未知的工具类型 {cfg.type}，工具名为 {cfg.name}")

    logger.info(f"已根据运行时配置构建 {len(tools)} 个工具")
    return tools

