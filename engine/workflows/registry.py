"""工作流注册表 - workflow_id -> 构图函数映射"""
from typing import Any, Awaitable, Callable, Dict, List
from langchain_core.language_models.chat_models import BaseChatModel
from engine.schemas.payload import ToolConfig
from engine.workflows.agent_chat import build_agent_chat_graph


ToolRunner = Callable[[Dict[str, Any]], Awaitable[Any]]


# 工作流构建函数类型
WorkflowBuilder = Callable[
    [BaseChatModel, Dict[str, ToolRunner], List[ToolConfig]],
    Any
]


# 工作流注册表
WORKFLOWS: Dict[str, WorkflowBuilder] = {
    "agent_chat": build_agent_chat_graph,
}


def get_workflow_builder(workflow_id: str) -> WorkflowBuilder:
    """根据 workflow_id 获取工作流构建函数

    :param workflow_id: 工作流 ID
    :return:
    :raises ValueError: 未知的 workflow_id
    """
    if workflow_id not in WORKFLOWS:
        raise ValueError(f"Unknown workflow_id: {workflow_id}")
    return WORKFLOWS[workflow_id]


def list_workflows() -> List[str]:
    """列出所有已注册的工作流 ID

    :return:
    """
    return list(WORKFLOWS.keys())

