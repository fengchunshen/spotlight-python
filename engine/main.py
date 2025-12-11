"""FastAPI 入口与 SSE 接口

单一业务接口: POST /v1/run_workflow
"""
import sys
import asyncio
from pathlib import Path
from contextlib import suppress

# 添加项目根目录到 Python 路径，支持直接运行此文件
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator, Any, Dict, List, Optional, Set
import traceback

from engine.config import config
from engine.schemas.payload import Payload, Message
from engine.models.llm_factory import build_llm
from engine.tools.loader import build_tools_from_runtime, ToolEventHooks
from engine.workflows.registry import get_workflow_builder, list_workflows
from engine.routers import knowledge as knowledge_router
from engine.sse.emitter import (
    format_tool_thinking,
    format_tool_start,
    format_tool_result,
    format_message_chunk,
    format_done,
    format_error,
    format_keepalive
)
from engine.logging_utils import get_logger


app = FastAPI(
    title="SpotLight Python 执行平面",
    description="基于 FastAPI + LangGraph 的工作流执行平面服务",
    version="0.1.0"
)

app.include_router(knowledge_router.router)



def safe_int(value: Any) -> int:
    """
    安全地将值转换为 int

    :param value: 需要转换的值
    :return:
    """
    if value is None:
        return 0

    if isinstance(value, (int, float)):
        return int(value)

    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return 0

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def to_plain_dict(value: Any) -> Optional[Dict[str, Any]]:
    """
    尝试将任意对象转换为字典

    :param value: 任意对象
    :return:
    """
    if value is None:
        return None

    if isinstance(value, dict):
        return value

    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except TypeError:
            return None

    if hasattr(value, "dict"):
        try:
            return value.dict()
        except TypeError:
            return None

    if hasattr(value, "__dict__"):
        try:
            return {
                key: val
                for key, val in vars(value).items()
                if not key.startswith("_")
            }
        except TypeError:
            return None

    return None


def normalize_usage_payload(payload: Any) -> Optional[Dict[str, int]]:
    """
    标准化解析 usage 数据

    :param payload: 可能包含 usage 的对象或字典
    :return:
    """
    if payload is None:
        return None

    visited: Set[int] = set()
    stack: List[Any] = [payload]
    nested_keys = (
        "usage",
        "token_usage",
        "usage_metadata",
        "llm_output",
        "response_metadata",
        "metadata",
    )

    while stack:
        current = stack.pop()
        if current is None:
            continue

        identity = id(current)
        if identity in visited:
            continue
        visited.add(identity)

        plain_dict = to_plain_dict(current)
        if plain_dict:
            prompt = plain_dict.get("prompt_tokens")
            completion = plain_dict.get("completion_tokens")
            total = plain_dict.get("total_tokens")

            if any(item is not None for item in (prompt, completion, total)):
                prompt_value = safe_int(prompt) if prompt is not None else 0
                if prompt_value == 0:
                    prompt_value = safe_int(plain_dict.get("input_tokens"))

                if prompt_value == 0 and plain_dict.get("prompt_tokens_details"):
                    details = to_plain_dict(plain_dict.get("prompt_tokens_details"))
                    if details:
                        prompt_value = sum(safe_int(val) for val in details.values())

                completion_value = safe_int(completion) if completion is not None else 0
                if completion_value == 0:
                    completion_value = safe_int(plain_dict.get("output_tokens"))

                if completion_value == 0 and plain_dict.get("completion_tokens_details"):
                    details = to_plain_dict(plain_dict.get("completion_tokens_details"))
                    if details:
                        completion_value = sum(safe_int(val) for val in details.values())

                total_value = safe_int(total) if total is not None else prompt_value + completion_value
                if total_value == 0:
                    total_value = prompt_value + completion_value

                return {
                    "prompt_tokens": prompt_value,
                    "completion_tokens": completion_value,
                    "total_tokens": total_value
                }

            for key in nested_keys:
                nested_value = plain_dict.get(key)
                if nested_value is not None:
                    stack.append(nested_value)

        for attr in nested_keys:
            if hasattr(current, attr):
                stack.append(getattr(current, attr))

    return None


def extract_usage_from_chunk(chunk: Any, event_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, int]]:
    """
    提取流式 chunk 中的 usage 数据

    :param chunk: LangChain chunk 对象或原始字典
    :param event_data: 原始事件数据，作为兜底
    :return:
    """
    usage = normalize_usage_payload(chunk)
    if usage:
        return usage

    return normalize_usage_payload(event_data)


def extract_usage_from_output(output: Any) -> Optional[Dict[str, int]]:
    """
    提取最终输出对象中的 usage 数据

    :param output: LangGraph on_chat_model_end 的输出对象
    :return:
    """
    return normalize_usage_payload(output)


IDENTITY_KEYWORDS: List[str] = [
    "你是谁",
    "是谁开发",
    "介绍一下你",
    "身份",
    "who are you",
    "what are you",
    "your identity",
]


IDENTITY_RESPONSE = (
    "我是 SpotLight Python 执行平面的智能代理，负责调度工作流与工具以完成你的任务。"
)


def is_identity_query(messages: List[Message]) -> bool:
    """
    判断用户是否在询问身份

    :param messages: 会话消息列表
    :return:
    """
    if not messages:
        return False

    latest_user = next((msg for msg in reversed(messages) if msg.role == "user"), None)
    if latest_user is None:
        return False

    if not isinstance(latest_user.content, str):
        return False

    content = latest_user.content.strip().lower()
    for keyword in IDENTITY_KEYWORDS:
        if keyword in content:
            return True

    return False


@app.get("/")
async def root():
    """根路径 - 返回服务信息"""
    return {
        "service": "SpotLight Python Engine",
        "version": "0.1.0",
        "workflows": list_workflows()
    }


@app.get("/health")
async def health():
    """健康检查接口"""
    return {"status": "healthy"}


@app.post("/v1/run_workflow")
async def run_workflow(payload: Payload):
    """执行工作流 - 唯一业务接口

    :param payload: 执行载荷，符合《通用执行载荷协议标准》
    :return:
    """
    
    async def event_stream() -> AsyncGenerator[str, None]:
        """SSE 事件流生成器"""
        trace_id = payload.task_meta.trace_id
        logger = get_logger(trace_id)

        sse_queue: asyncio.Queue[Any] = asyncio.Queue()
        stream_complete_marker = object()
        keepalive_interval = config.SSE_KEEPALIVE_INTERVAL
        keepalive_task: Optional[asyncio.Task[Any]] = None

        async def emit(event: str) -> None:
            await sse_queue.put(event)

        async def emit_tool_start(tool_name: str, args: Dict[str, Any]) -> None:
            await emit(format_tool_start(tool_name, args, trace_id))

        async def emit_tool_result(tool_name: str, result: Any) -> None:
            await emit(format_tool_result(tool_name, result, trace_id))

        async def emit_tool_error(tool_name: str, exc: Exception) -> None:
            await emit(format_tool_result(tool_name, {"error": str(exc)}, trace_id))

        tool_event_hooks: ToolEventHooks = {
            "on_start": emit_tool_start,
            "on_result": emit_tool_result,
            "on_error": emit_tool_error,
        }
        tool_events_via_hooks = True

        async def run_flow() -> None:
            usage_data = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
            finish_reason = "stop"
            accumulated_content = ""
            stream_error: Optional[Exception] = None

            try:
                workflow_id = payload.task_meta.workflow_id
                logger.info(f"开始执行工作流: {workflow_id}")
                await emit(format_tool_thinking("正在初始化工作流...", trace_id))

                if is_identity_query(payload.input.messages):
                    logger.info("检测到身份查询，返回预置回复")
                    await emit(format_message_chunk(IDENTITY_RESPONSE, trace_id))
                    await emit(format_done(
                        usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                        finish_reason="identity_guard",
                        trace_id=trace_id
                    ))
                    return

                model_cfg = payload.runtime_config.model
                logger.info("正在构建 LLM 客户端")
                await emit(format_tool_thinking("正在连接模型服务...", trace_id))
                llm = build_llm(model_cfg)

                logger.info(f"正在加载 {len(payload.runtime_config.tools)} 个工具")
                await emit(format_tool_thinking("正在加载工具...", trace_id))
                tools = build_tools_from_runtime(
                    payload.runtime_config.tools,
                    payload.runtime_config.vault,
                    trace_id,
                    tool_event_hooks=tool_event_hooks
                )

                try:
                    builder = get_workflow_builder(workflow_id)
                except ValueError as e:
                    logger.error(f"非法的 workflow_id: {workflow_id}")
                    await emit(format_error(400, str(e), trace_id))
                    return

                logger.info("正在构建工作流图")
                await emit(format_tool_thinking("正在构建工作流...", trace_id))
                graph = builder(
                    llm=llm,
                    tools=tools,
                    tool_configs=payload.runtime_config.tools,
                    trace_id=trace_id,
                )

                init_state = {
                    "messages": [m.model_dump() for m in payload.input.messages],
                }

                logger.info("以流式模式执行工作流")
                await emit(format_tool_thinking("正在执行工作流...", trace_id))

                try:
                    async for event in graph.astream_events(init_state, version="v2"):
                        event_name = event.get("event", "")
                        event_data = event.get("data", {})

                        try:
                            if event_name in ("on_chat_model_stream", "on_chat_model_chunk"):
                                chunk = event_data.get("chunk")
                                content = ""

                                if chunk is not None:
                                    usage_from_chunk = extract_usage_from_chunk(chunk, event_data)
                                    if usage_from_chunk:
                                        usage_data.update(usage_from_chunk)

                                    if hasattr(chunk, "content"):
                                        content = chunk.content
                                    elif hasattr(chunk, "text"):
                                        content = chunk.text
                                    elif isinstance(chunk, dict):
                                        content = chunk.get("content", chunk.get("text", ""))
                                    elif isinstance(chunk, str):
                                        content = chunk
                                    else:
                                        content = str(chunk) if chunk else ""

                                    if content:
                                        accumulated_content += content
                                        await emit(format_message_chunk(content, trace_id))

                            elif event_name == "on_chat_model_end":
                                output = event_data.get("output")
                                usage_from_output = extract_usage_from_output(output)
                                if usage_from_output:
                                    usage_data.update(usage_from_output)

                            elif event_name == "on_tool_start" and not tool_events_via_hooks:
                                tool_name = event_data.get("name", "unknown")
                                input_data = event_data.get("input", {})
                                await emit(format_tool_start(tool_name, input_data, trace_id))

                            elif event_name == "on_tool_end" and not tool_events_via_hooks:
                                tool_name = event_data.get("name", "unknown")
                                output = event_data.get("output")
                                await emit(format_tool_result(tool_name, output, trace_id))

                            elif event_name == "on_chain_end":
                                output = event_data.get("output", {})
                                if isinstance(output, dict) and "finish_reason" in output:
                                    finish_reason = output["finish_reason"]
                                elif hasattr(output, "finish_reason"):
                                    finish_reason = output.finish_reason

                        except Exception as event_error:
                            logger.warning(f"处理事件 {event_name} 时出错: {str(event_error)}")
                            stream_error = event_error
                            continue

                except Exception as stream_exception:
                    logger.error(f"流式执行出现异常: {str(stream_exception)}")
                    logger.error(traceback.format_exc())
                    stream_error = stream_exception
                    if accumulated_content:
                        await emit(format_message_chunk(accumulated_content, trace_id))

                if stream_error:
                    logger.warning(f"工作流执行结束但存在错误，总 tokens: {usage_data['total_tokens']}")
                else:
                    logger.info(f"工作流执行完成，总 tokens: {usage_data['total_tokens']}")

                if usage_data["total_tokens"] == 0 and accumulated_content:
                    logger.warning("无法从模型响应中提取 token 用量，使用默认值")

                await emit(format_done(usage=usage_data, finish_reason=finish_reason, trace_id=trace_id))
                logger.info("工作流执行成功结束")

            except Exception as exc:
                logger.error(f"工作流执行失败: {str(exc)}")
                logger.error(traceback.format_exc())
                error_msg = "工作流执行失败"
                if isinstance(exc, (ValueError, TypeError)):
                    error_msg = str(exc)
                await emit(format_error(code=500, msg=error_msg, trace_id=trace_id))

            finally:
                await sse_queue.put(stream_complete_marker)

        async def keepalive_loop() -> None:
            """定时推送保活事件"""
            try:
                while True:
                    await asyncio.sleep(keepalive_interval)
                    await emit(format_keepalive())
            except asyncio.CancelledError:
                raise

        workflow_task = asyncio.create_task(run_flow())
        if keepalive_interval > 0:
            keepalive_task = asyncio.create_task(keepalive_loop())

        while True:
            event_item = await sse_queue.get()
            if event_item is stream_complete_marker:
                break
            yield event_item

        if keepalive_task:
            keepalive_task.cancel()
            with suppress(asyncio.CancelledError):
                await keepalive_task

        await workflow_task
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

