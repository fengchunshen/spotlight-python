"""通用执行载荷 Payload 的 Pydantic 模型

符合《通用执行载荷协议标准》的实现
"""
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional


class TaskMeta(BaseModel):
    """任务元数据"""
    workflow_id: str
    trace_id: str
    user_id: str


class Message(BaseModel):
    """消息模型"""
    role: Literal["system", "user", "assistant", "tool"]
    content: Any


class InputContext(BaseModel):
    """输入上下文"""
    messages: List[Message]
    variables: Dict[str, Any] = Field(default_factory=dict)


class ToolConfig(BaseModel):
    """工具配置"""
    type: Literal["NATIVE", "HTTP"]
    name: str
    description: Optional[str] = None
    parameter_schema: Dict[str, Any] = Field(default_factory=dict)
    execution_config: Dict[str, Any] = Field(default_factory=dict)


class ModelConfig(BaseModel):
    """模型配置"""
    provider: Optional[str] = None  # 厂商标识，Python 端不使用，仅用于协议兼容
    model_name: str
    base_url: str
    api_key: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    supports_reasoning_events: bool = Field(
        default=False,
        description="模型是否输出 reasoning/rethinking 片段"
    )


class RuntimeConfig(BaseModel):
    """运行时配置"""
    model: ModelConfig
    tools: List[ToolConfig] = Field(default_factory=list)
    vault: Dict[str, str] = Field(default_factory=dict)


class Payload(BaseModel):
    """执行载荷"""
    task_meta: TaskMeta
    input: InputContext
    runtime_config: RuntimeConfig

