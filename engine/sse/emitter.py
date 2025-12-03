"""SSE 事件封装 - 统一格式化 SSE 事件

符合《SSE 流式透传与透明代理协议标准》
"""
import json
from uuid import uuid4
from typing import Any, Dict, Optional


def format_sse(event: str, data: Dict[str, Any], event_id: Optional[str] = None) -> str:
    """格式化 SSE 事件

    :param event: 事件类型（如 tool_thinking, message_chunk, done, error 等）
    :param data: 事件数据（必须是可序列化为 JSON 的字典）
    :param event_id: 事件 ID（可选，默认自动生成）
    :return:
    """
    eid = event_id or str(uuid4())
    return f"id: {eid}\nevent: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def format_keepalive() -> str:
    """生成 SSE 保活注释"""
    return ": keep-alive\n\n"


def format_ping() -> str:
    """生成 ping 事件"""
    return format_sse("ping", {"msg": "keep-alive"})


def format_tool_thinking(msg: str, trace_id: str) -> str:
    """格式化工具思考事件

    :param msg: 思考内容
    :param trace_id: 链路追踪 ID
    :return:
    """
    return format_sse("tool_thinking", {"msg": msg, "trace_id": trace_id})


def format_tool_start(tool_name: str, args: Dict[str, Any], trace_id: str) -> str:
    """格式化工具开始执行事件

    :param tool_name: 工具名称
    :param args: 工具参数
    :param trace_id: 链路追踪 ID
    :return:
    """
    return format_sse("tool_start", {
        "tool_name": tool_name,
        "args": args,
        "trace_id": trace_id
    })


def format_tool_result(tool_name: str, result: Any, trace_id: str) -> str:
    """格式化工具执行结果事件

    :param tool_name: 工具名称
    :param result: 工具执行结果
    :param trace_id: 链路追踪 ID
    :return:
    """
    return format_sse("tool_result", {
        "tool_name": tool_name,
        "result": result,
        "trace_id": trace_id
    })


def format_message_chunk(content: str, trace_id: str) -> str:
    """格式化消息片段事件

    :param content: 消息内容
    :param trace_id: 链路追踪 ID
    :return:
    """
    return format_sse("message_chunk", {"content": content, "trace_id": trace_id})


def format_done(usage: Dict[str, int], finish_reason: str, trace_id: str) -> str:
    """格式化完成事件

    :param usage: token 使用量字典，支持整型兼容
    :param finish_reason: 结束原因（如 stop, length, tool_calls）
    :param trace_id: 链路追踪 ID
    :return:
    """
    # 向后兼容：如果传入 int，转换为字典格式
    if isinstance(usage, int):
        usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": usage
        }
    
    return format_sse("done", {
        "usage": usage,
        "finish_reason": finish_reason,
        "trace_id": trace_id
    })


def format_error(code: int, msg: str, trace_id: str) -> str:
    """格式化错误事件

    :param code: 错误码
    :param msg: 错误消息（应做安全过滤，不泄露敏感信息）
    :param trace_id: 链路追踪 ID
    :return:
    """
    return format_sse("error", {
        "code": code,
        "msg": msg,
        "trace_id": trace_id
    })

