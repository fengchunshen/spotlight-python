"""FastAPI 入口与 SSE 接口

单一业务接口: POST /v1/run_workflow
"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
import traceback

from engine.schemas.payload import Payload
from engine.models.llm_factory import build_llm
from engine.tools.loader import build_tools_from_runtime
from engine.workflows.registry import get_workflow_builder, list_workflows
from engine.sse.emitter import (
    format_tool_thinking,
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
            logger.info(f"Starting workflow: {workflow_id}")
            
            # 发送初始思考事件
            yield format_tool_thinking("正在初始化工作流...", trace_id)
            
            # 2. 构建 LLM
            logger.info("Building LLM client")
            yield format_tool_thinking("正在连接模型服务...", trace_id)
            llm = build_llm(payload.runtime_config.model)
            
            # 3. 构建工具集
            logger.info(f"Loading {len(payload.runtime_config.tools)} tools")
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
                logger.error(f"Invalid workflow_id: {workflow_id}")
                yield format_error(400, str(e), trace_id)
                return
            
            # 5. 构建工作流图
            logger.info("Building workflow graph")
            yield format_tool_thinking("正在构建工作流...", trace_id)
            graph = builder(llm=llm)
            
            # 6. 准备初始状态
            init_state = {
                "messages": [m.model_dump() for m in payload.input.messages],
            }
            
            # 7. 执行工作流
            logger.info("Executing workflow")
            yield format_tool_thinking("正在执行工作流...", trace_id)
            
            final_state = graph.invoke(init_state)
            
            # 8. 提取结果
            messages = final_state.get("messages", [])
            if messages:
                last_message = messages[-1]
                answer = last_message.get("content", "")
                
                # 输出消息片段（后续可拆分为流式）
                logger.info(f"Workflow completed, response length: {len(answer)}")
                yield format_message_chunk(answer, trace_id)
            else:
                logger.warning("No messages in final state")
                yield format_message_chunk("", trace_id)
            
            # 9. 输出完成事件
            # TODO: 从 LLM 响应中提取实际的 token usage
            yield format_done(usage=0, finish_reason="stop", trace_id=trace_id)
            logger.info("Workflow execution completed successfully")
            
        except Exception as e:
            # 捕获所有异常并转换为 SSE error 事件
            logger.error(f"Workflow execution failed: {str(e)}")
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

