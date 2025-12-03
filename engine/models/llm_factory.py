"""LLM 工厂 - 基于 ModelConfig 构造 ChatOpenAI

对接 OneAPI（统一 OpenAI 协议）
"""
from langchain_openai import ChatOpenAI
from engine.schemas.payload import ModelConfig


def build_llm(model_cfg: ModelConfig) -> ChatOpenAI:
    """根据模型配置构建 LLM 客户端

    :param model_cfg: 模型配置对象
    :return:
    """
    return ChatOpenAI(
        model=model_cfg.model_name,
        openai_api_key=model_cfg.api_key,
        openai_api_base=model_cfg.base_url,
        temperature=model_cfg.temperature,
        max_tokens=model_cfg.max_tokens,
        streaming=True,  # 为后续 SSE 流式输出做准备
    )

