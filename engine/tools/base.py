"""原生工具基类

所有原生工具必须继承 BaseNativeTool 并实现 run 方法
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Type
from pydantic import BaseModel


class BaseNativeTool(ABC):
    """原生工具抽象基类"""
    
    name: str
    description: str
    args_schema: Type[BaseModel]

    @abstractmethod
    def run(self, args: BaseModel, context: Dict[str, Any]) -> Any:
        """执行工具

        :param args: 工具参数，符合 args_schema 定义
        :param context: 执行上下文（可包含 trace_id、user_id 等）
        :return:
        """
        ...

    @classmethod
    def json_schema(cls) -> Dict[str, Any]:
        """获取参数的 JSON Schema

        :return:
        """
        return cls.args_schema.model_json_schema()

