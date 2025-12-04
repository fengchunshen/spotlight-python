"""基础对话型 LangGraph 工作流

实现基于 LLM 的对话能力，并支持 LangChain function calling 工具执行
"""
import json
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypedDict
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.exceptions import LangChainException
from engine.schemas.payload import ToolConfig
from engine.logging_utils import get_logger


class AgentState(TypedDict):
    """Agent 状态定义"""
    messages: List[Dict[str, Any]]


def build_agent_chat_graph(
    llm: BaseChatModel,
    tools: Dict[str, Callable[[Dict[str, Any]], Awaitable[Any]]],
    tool_configs: List[ToolConfig],
    trace_id: Optional[str] = None,
) -> Any:
    """构建支持工具调用的对话工作流

    :param llm: LLM 客户端
    :param tools: 已加载工具映射
    :param tool_configs: 工具配置列表
    :param trace_id: 链路追踪 ID，用于日志记录
    :return: 编译后的 LangGraph 工作流
    """
    graph = StateGraph(AgentState)
    llm_with_tools = _bind_llm_tools(llm, tool_configs)
    logger = get_logger(trace_id)

    async def llm_node(state: AgentState) -> AgentState:
        """LLM 节点 - 处理对话与工具调用"""
        loop_guard = 0
        while loop_guard < 5:
            try:
                lc_messages = _convert_messages(state["messages"], logger)
            except Exception as exc:
                logger.error(f"消息转换失败: {str(exc)}")
                raise ValueError("消息格式错误，无法转换为 LangChain 消息格式") from exc

            try:
                response = await llm_with_tools.ainvoke(lc_messages)
            except LangChainException as exc:
                logger.error(f"LLM 调用失败: {str(exc)}")
                raise RuntimeError("模型调用失败，请检查模型配置和网络连接") from exc
            except Exception as exc:
                logger.error(f"LLM 调用出现未知错误: {str(exc)}")
                raise RuntimeError("模型调用出现异常") from exc

            assistant_message = _serialize_assistant_message(response)
            state["messages"].append(assistant_message)

            tool_calls = _extract_tool_calls(response)
            if not tool_calls:
                return state

            try:
                tool_messages = await _execute_tool_calls(tool_calls, tools, logger)
            except Exception as exc:
                logger.error(f"工具调用失败: {str(exc)}")
                raise RuntimeError(f"工具执行失败: {str(exc)}") from exc

            state["messages"].extend(tool_messages)
            loop_guard += 1

        logger.warning("工具调用超过最大迭代次数 (5)")
        raise RuntimeError("Tool calling exceeded maximum iterations")

    graph.add_node("llm", llm_node)
    graph.set_entry_point("llm")
    graph.add_edge("llm", END)

    return graph.compile()


def _bind_llm_tools(
    llm: BaseChatModel,
    tool_configs: List[ToolConfig],
) -> BaseChatModel:
    """绑定工具定义，如果没有工具则返回原始 LLM

    :param llm: 原始 LLM 实例
    :param tool_configs: 工具配置列表
    :return: 绑定后的 LLM
    """
    if not tool_configs:
        return llm

    tool_definitions = []
    for cfg in tool_configs:
        schema = cfg.parameter_schema or {"type": "object", "properties": {}, "required": []}
        tool_definitions.append({
            "type": "function",
            "function": {
                "name": cfg.name,
                "description": cfg.description or "",
                "parameters": schema,
            },
        })

    return llm.bind_tools(tool_definitions)


def _convert_messages(
    messages: List[Dict[str, Any]],
    logger: Optional[Any] = None,
) -> List[Any]:
    """将内部消息结构转换为 LangChain 消息

    支持多模态输入：
    - 字符串格式：content = "text"
    - 多模态格式：content = [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "..."}}]

    :param messages: 当前状态消息列表
    :param logger: 日志记录器，用于记录多模态内容类型
    :return: LangChain 消息对象列表
    """
    lc_messages: List[Any] = []
    for idx, msg in enumerate(messages):
        role = msg.get("role")
        content = msg.get("content", "")

        if logger:
            content_type = _detect_content_type(content)
            if content_type != "text":
                logger.debug(f"消息 {idx} ({role}) 包含多模态内容: {content_type}")

        try:
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                additional_kwargs = {}
                if "tool_calls" in msg:
                    additional_kwargs["tool_calls"] = msg["tool_calls"]
                lc_messages.append(AIMessage(content=content, additional_kwargs=additional_kwargs))
            elif role == "tool":
                lc_messages.append(
                    ToolMessage(
                        content=_stringify_tool_content(content),
                        tool_call_id=msg.get("tool_call_id", ""),
                    )
                )
            else:
                if logger:
                    logger.warning(f"未知的消息角色: {role}，跳过该消息")
        except Exception as exc:
            if logger:
                logger.error(f"转换消息 {idx} ({role}) 时出错: {str(exc)}")
            raise ValueError(f"消息格式错误，无法创建 {role} 消息") from exc

    return lc_messages


def _detect_content_type(content: Any) -> str:
    """检测消息内容类型

    :param content: 消息内容
    :return: 内容类型描述
    """
    if content is None:
        return "empty"
    if isinstance(content, str):
        return "text"
    if isinstance(content, list):
        types = []
        for item in content:
            if isinstance(item, dict):
                item_type = item.get("type", "unknown")
                types.append(item_type)
            else:
                types.append(type(item).__name__)
        return f"multimodal[{', '.join(types)}]"
    return type(content).__name__


def _serialize_assistant_message(response: AIMessage) -> Dict[str, Any]:
    """把 LLM 响应转换为内部消息结构

    :param response: LLM 输出
    :return: 内部消息结构
    """
    serialized: Dict[str, Any] = {
        "role": "assistant",
        "content": response.content or "",
    }

    tool_calls = _extract_tool_calls(response)
    if tool_calls:
        serialized["tool_calls"] = tool_calls

    return serialized


def _extract_tool_calls(response: AIMessage) -> List[Dict[str, Any]]:
    """抽取 LLM 返回的工具调用定义

    :param response: LLM 输出
    :return: 工具调用列表
    """
    normalized_calls: List[Dict[str, Any]] = []
    raw_calls: List[Any] = []

    if getattr(response, "tool_calls", None):
        raw_calls.extend(response.tool_calls)

    additional = response.additional_kwargs.get("tool_calls")
    if isinstance(additional, list):
        raw_calls.extend(additional)

    for call in raw_calls:
        normalized = _normalize_tool_call(call)
        if normalized:
            normalized_calls.append(normalized)

    return normalized_calls


def _normalize_tool_call(call: Any) -> Dict[str, Any]:
    """
    规范化工具调用结构

    :param call: LLM 返回的工具调用定义
    :return:
    """
    call_dict: Dict[str, Any]
    if isinstance(call, dict):
        call_dict = call
    elif hasattr(call, "model_dump"):
        call_dict = call.model_dump()
    elif hasattr(call, "dict"):
        call_dict = call.dict()
    else:
        return {}

    if "function" in call_dict:
        function_meta = call_dict.get("function") or {}
        return {
            "id": call_dict.get("id", ""),
            "type": call_dict.get("type", "function"),
            "function": {
                "name": function_meta.get("name", ""),
                "arguments": _stringify_arguments(function_meta.get("arguments")),
            },
        }

    arguments = call_dict.get("arguments")
    if arguments is None:
        arguments = call_dict.get("args")

    return {
        "id": call_dict.get("id", ""),
        "type": call_dict.get("type", "function"),
        "function": {
            "name": call_dict.get("name", ""),
            "arguments": _stringify_arguments(arguments),
        },
    }


async def _execute_tool_calls(
    tool_calls: List[Dict[str, Any]],
    tools: Dict[str, Callable[[Dict[str, Any]], Awaitable[Any]]],
    logger: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """执行工具调用并生成 tool 消息

    :param tool_calls: LLM 工具调用定义
    :param tools: 已加载工具映射
    :param logger: 日志记录器
    :return: 工具返回的消息列表
    """
    tool_messages: List[Dict[str, Any]] = []
    for call in tool_calls:
        function_meta = call.get("function", {}) if isinstance(call, dict) else {}
        if not isinstance(function_meta, dict):
            function_meta = {}
        tool_name = function_meta.get("name")
        args_raw = function_meta.get("arguments", "{}")
        call_id = call.get("id", "")

        if not tool_name:
            if logger:
                logger.error("LLM 返回的 tool call 缺少名称")
            raise ValueError("LLM 返回的 tool call 缺少名称")
        if tool_name not in tools:
            if logger:
                logger.error(f"工具 {tool_name} 未在运行时加载，可用工具: {list(tools.keys())}")
            raise ValueError(f"工具 {tool_name} 未在运行时加载")

        try:
            args = _parse_arguments(args_raw)
            if logger:
                logger.debug(f"执行工具 {tool_name}，参数: {args}")
            result = await tools[tool_name](args)
        except Exception as exc:
            if logger:
                logger.error(f"工具 {tool_name} 执行失败: {str(exc)}")
            raise RuntimeError(f"工具 {tool_name} 执行失败: {str(exc)}") from exc

        tool_messages.append({
            "role": "tool",
            "name": tool_name,
            "tool_call_id": call_id,
            "content": result,
        })

    return tool_messages


def _parse_arguments(arguments: Any) -> Dict[str, Any]:
    """解析工具参数

    :param arguments: JSON 字符串或字典参数
    :return: 解析后的参数字典
    """
    if not arguments:
        return {}

    if isinstance(arguments, dict):
        return arguments

    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
            if isinstance(parsed, dict):
                return parsed
            raise ValueError("工具参数必须是 JSON 对象")
        except json.JSONDecodeError as exc:
            raise ValueError("工具参数不是合法 JSON") from exc

    raise ValueError("工具参数必须是 JSON 字符串或对象")


def _stringify_tool_content(content: Any) -> str:
    """将工具输出转换为字符串

    :param content: 工具返回内容
    :return: 字符串形式
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _stringify_arguments(arguments: Any) -> str:
    """
    将工具参数转换为 JSON 字符串

    :param arguments: 任意形式的工具参数
    :return:
    """
    if not arguments:
        return ""
    if isinstance(arguments, str):
        return arguments
    try:
        return json.dumps(arguments, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(arguments)

