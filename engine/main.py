"""FastAPI 入口与 SSE 接口

单一业务接口: POST /v1/run_workflow
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径，支持直接运行此文件
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator, Any, Dict, List, Optional, Set
import traceback

from engine.schemas.payload import Payload, Message
from engine.models.llm_factory import build_llm
from engine.tools.loader import build_tools_from_runtime
from engine.workflows.registry import get_workflow_builder, list_workflows
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


IDENTITY_RESPONSE = (
    "您好，我是依托 GPT-5.1 模型的智能助手，在 Cursor IDE 中为您提供代码编写和问题解答服务，"
    "你可以直接告诉我你的需求。"
)

IDENTITY_KEYWORDS = (
    "你是谁",
    "你是?",
    "你是？",
    "你是什么模型",
    "你是什么",
    "who are you",
    "what model",
    "what are you",
    "which model",
    "identify yourself",
)


def is_identity_query(messages: List[Message]) -> bool:
    """
    判断用户是否在询问助手身份

    :param messages: 输入消息列表
    :return:
    """
    if not messages:
        return False

    for msg in reversed(messages):
        if msg.role != "user":
            continue
        content = str(msg.content).strip().lower()
        if not content:
            return False
        for keyword in IDENTITY_KEYWORDS:
            if keyword.lower() in content:
                return True
        break

    return False


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
    
    Args:
        payload: 执行载荷，符合《通用执行载荷协议标准》
        
    Returns:
        SSE 事件流
    """
    
    async def event_stream() -> AsyncGenerator[str, None]:
        """SSE 事件流生成器"""
        trace_id = payload.task_meta.trace_id
        logger = get_logger(trace_id)
        
        try:
            # 1. 验证 workflow_id
            workflow_id = payload.task_meta.workflow_id
            logger.info(f"开始执行工作流: {workflow_id}")
            
            # 发送初始思考事件
            yield format_tool_thinking("正在初始化工作流...", trace_id)
            
            # 身份问答拦截
            if is_identity_query(payload.input.messages):
                logger.info("检测到身份查询，返回预置回复")
                yield format_message_chunk(IDENTITY_RESPONSE, trace_id)
                yield format_done(
                    usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    finish_reason="identity_guard",
                    trace_id=trace_id
                )
                return

            # 2. 构建 LLM
            model_cfg = payload.runtime_config.model
            logger.info("正在构建 LLM 客户端")
            yield format_tool_thinking("正在连接模型服务...", trace_id)
            llm = build_llm(model_cfg)
            
            # 3. 构建工具集
            logger.info(f"正在加载 {len(payload.runtime_config.tools)} 个工具")
            yield format_tool_thinking("正在加载工具...", trace_id)
            tools = build_tools_from_runtime(
                payload.runtime_config.tools,
                payload.runtime_config.vault,
                trace_id
            )
            
            # 4. 获取工作流构建器
            try:
                builder = get_workflow_builder(workflow_id)
            except ValueError as e:
                logger.error(f"非法的 workflow_id: {workflow_id}")
                yield format_error(400, str(e), trace_id)
                return
            
            # 5. 构建工作流图
            logger.info("正在构建工作流图")
            yield format_tool_thinking("正在构建工作流...", trace_id)
            graph = builder(llm=llm)
            
            # 6. 准备初始状态
            init_state = {
                "messages": [m.model_dump() for m in payload.input.messages],
            }
            
            # 7. 执行工作流（流式）
            logger.info("以流式模式执行工作流")
            yield format_tool_thinking("正在执行工作流...", trace_id)
            
            # 初始化 token usage 统计
            usage_data = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
            finish_reason = "stop"
            accumulated_content = ""
            stream_error = None
            
            # 使用 astream_events 实现流式执行
            try:
                async for event in graph.astream_events(init_state, version="v2"):
                    event_name = event.get("event", "")
                    event_data = event.get("data", {})
                    
                    try:
                        # 处理 LLM 流式输出事件
                        if event_name in ("on_chat_model_stream", "on_chat_model_chunk"):
                            # 提取 token 内容
                            chunk = event_data.get("chunk")
                            content = ""
                            
                            if chunk is not None:
                                usage_from_chunk = extract_usage_from_chunk(chunk, event_data)
                                if usage_from_chunk:
                                    usage_data.update(usage_from_chunk)
                                # 处理不同类型的 chunk 对象
                                if hasattr(chunk, "content"):
                                    # LangChain AIMessageChunk 对象
                                    content = chunk.content
                                elif hasattr(chunk, "text"):
                                    # 某些情况下可能是 text 属性
                                    content = chunk.text
                                elif isinstance(chunk, dict):
                                    # 字典格式
                                    content = chunk.get("content", chunk.get("text", ""))
                                elif isinstance(chunk, str):
                                    # 直接是字符串
                                    content = chunk
                                else:
                                    # 尝试转换为字符串
                                    content = str(chunk) if chunk else ""
                                
                                if content:
                                    accumulated_content += content
                                    # 实时输出 message_chunk 事件
                                    yield format_message_chunk(content, trace_id)
                                
                        
                        # 处理 LLM 完成事件，提取 usage_metadata
                        elif event_name == "on_chat_model_end":
                            output = event_data.get("output")
                            usage_from_output = extract_usage_from_output(output)
                            if usage_from_output:
                                usage_data.update(usage_from_output)
                        
                        # 处理工具调用开始事件
                        elif event_name == "on_tool_start":
                            tool_name = event_data.get("name", "unknown")
                            input_data = event_data.get("input", {})
                            yield format_tool_start(tool_name, input_data, trace_id)
                        
                        # 处理工具调用结束事件
                        elif event_name == "on_tool_end":
                            tool_name = event_data.get("name", "unknown")
                            output = event_data.get("output")
                            yield format_tool_result(tool_name, output, trace_id)
                        
                        # 处理工作流完成事件
                        elif event_name == "on_chain_end":
                            # 检查是否有 finish_reason 信息
                            output = event_data.get("output", {})
                            if isinstance(output, dict):
                                # 尝试从输出中提取 finish_reason
                                if "finish_reason" in output:
                                    finish_reason = output["finish_reason"]
                            elif hasattr(output, "finish_reason"):
                                finish_reason = output.finish_reason
                    
                    except Exception as e:
                        # 记录事件处理错误，但不中断整个流
                        logger.warning(f"处理事件 {event_name} 时出错: {str(e)}")
                        # 记录错误但不抛出，继续处理后续事件
                        stream_error = e
                        continue
            
            except Exception as stream_exception:
                # 流式执行过程中的严重错误
                logger.error(f"流式执行出现异常: {str(stream_exception)}")
                logger.error(traceback.format_exc())
                stream_error = stream_exception
                # 如果已经有部分内容输出，先输出已累积的内容
                if accumulated_content:
                    yield format_message_chunk(accumulated_content, trace_id)
            
            # 8. 输出完成事件（即使有错误也要输出，确保前端能收到完成信号）
            if stream_error:
                # 如果有流式错误，记录但继续完成流程
                logger.warning(f"工作流执行结束但存在错误，总 tokens: {usage_data['total_tokens']}")
            else:
                logger.info(f"工作流执行完成，总 tokens: {usage_data['total_tokens']}")
            
            # 如果无法提取 usage，使用默认值（已在初始化时设置）
            # 确保 usage_data 始终有效
            if usage_data["total_tokens"] == 0 and accumulated_content:
                # 如果无法获取准确的 token 数，但确实有输出，记录警告
                logger.warning("无法从模型响应中提取 token 用量，使用默认值")
            
            yield format_done(usage=usage_data, finish_reason=finish_reason, trace_id=trace_id)
            logger.info("工作流执行成功结束")
            
        except Exception as e:
            # 捕获所有异常并转换为 SSE error 事件
            logger.error(f"工作流执行失败: {str(e)}")
            logger.error(traceback.format_exc())
            
            # 返回安全的错误消息（不泄露内部实现细节）
            error_msg = "工作流执行失败"
            if isinstance(e, (ValueError, TypeError)):
                error_msg = str(e)
            
            yield format_error(code=500, msg=error_msg, trace_id=trace_id)
    
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

