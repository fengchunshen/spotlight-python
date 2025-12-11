from typing import Any

from pydantic import BaseModel, Field


class TaskMeta(BaseModel):
    """任务元信息"""

    trace_id: str = Field(..., alias="trace_id")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }


class KnowledgeCreateRequest(BaseModel):
    """知识库创建请求"""

    task_meta: TaskMeta
    kb_id: str | None = Field(default=None, description="可选的知识库 ID，未提供则自动生成")
    kb_name: str
    owner: str
    tenant: str
    visibility: str = Field(default="private", description="可见性标识")
    description: str | None = None
    embedding_model: str
    vector_store_config: dict[str, Any] | None = None

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }


class KnowledgeDeleteRequest(BaseModel):
    """知识库删除请求"""

    task_meta: TaskMeta
    kb_id: str
    owner: str
    tenant: str
    soft_delete: bool = False

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }


class KnowledgeUpdateRequest(BaseModel):
    """知识库更新请求"""

    task_meta: TaskMeta
    kb_id: str
    kb_name: str | None = None
    description: str | None = None
    visibility: str | None = None
    embedding_model: str | None = None
    vector_store_config: dict[str, Any] | None = None

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }


class KnowledgeListRequest(BaseModel):
    """知识库列表查询请求"""

    task_meta: TaskMeta
    owner: str | None = None
    tenant: str | None = None
    page: int = 1
    size: int = 20

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }


class KnowledgeDetailRequest(BaseModel):
    """知识库详情请求"""

    task_meta: TaskMeta
    kb_id: str

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }


class BaseKnowledgeResponse(BaseModel):
    """知识库基础响应"""

    trace_id: str

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }


class KnowledgeSummary(BaseModel):
    """知识库摘要"""

    kb_id: str
    kb_name: str
    description: str | None = None
    kb_type: str
    visibility: str
    owner: str
    tenant: str
    embedding_model: str
    created_at: str


class KnowledgeCreateResponse(BaseKnowledgeResponse):
    """创建知识库响应"""

    kb: KnowledgeSummary


class KnowledgeDeleteResponse(BaseKnowledgeResponse):
    """删除知识库响应"""

    result: str


class KnowledgeUpdateResponse(BaseKnowledgeResponse):
    """更新知识库响应"""

    kb: KnowledgeSummary


class KnowledgeListResponse(BaseKnowledgeResponse):
    """知识库列表响应"""

    total: int
    items: list[KnowledgeSummary]


class KnowledgeDetailResponse(BaseKnowledgeResponse):
    """知识库详情响应"""

    kb: KnowledgeSummary


class MilvusTestRequest(BaseModel):
    """Milvus 连接测试请求"""

    task_meta: TaskMeta
    milvus_uri: str | None = None
    milvus_token: str | None = None
    milvus_db: str | None = None

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }


class MilvusTestResponse(BaseKnowledgeResponse):
    """Milvus 连接测试响应"""

    status: str
    message: str
    used_uri: str
    used_db: str


class MilvusTestWriteRequest(BaseModel):
    """Milvus 写入测试请求"""

    task_meta: TaskMeta
    kb_id: str
    content: str | None = None
    embedding_dim: int = 1536

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }


class MilvusTestWriteResponse(BaseKnowledgeResponse):
    """Milvus 写入测试响应"""

    status: str
    message: str
    collection: str
    rows: int

