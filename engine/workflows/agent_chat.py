"""基础对话型 LangGraph 工作流

实现基于 LLM 的对话能力，默认不引入工具节点
为后续扩展 function calling 和工具执行预留挂载点
"""
from typing import Any, Dict, List, TypedDict
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.language_models.chat_models import BaseChatModel


class AgentState(TypedDict):
    """Agent 状态定义"""
    messages: List[Dict[str, Any]]


def build_agent_chat_graph(llm: BaseChatModel):
    """构建对话 Agent 工作流图
    
    Args:
        llm: LLM 客户端
        
    Returns:
        编译后的 LangGraph 工作流
    """
    graph = StateGraph(AgentState)

    def llm_node(state: AgentState) -> AgentState:
        """LLM 节点 - 处理对话"""
        # 转换消息格式
        lc_messages = []
        for msg in state["messages"]:
            role = msg["role"]
            content = msg["content"]
            
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            # tool 消息暂时忽略
        
        # 调用 LLM
        resp = llm.invoke(lc_messages)
        
        # 添加 assistant 回复到消息列表
        state["messages"].append({
            "role": "assistant",
            "content": resp.content
        })
        
        return state

    # 构建图结构
    graph.add_node("llm", llm_node)
    graph.set_entry_point("llm")
    graph.add_edge("llm", END)

    return graph.compile()

