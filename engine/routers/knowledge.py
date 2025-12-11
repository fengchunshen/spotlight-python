from fastapi import APIRouter, HTTPException, status

from engine.logging_utils import get_logger
from engine.schemas.knowledge import (
    KnowledgeCreateRequest,
    KnowledgeCreateResponse,
    KnowledgeDeleteRequest,
    KnowledgeDeleteResponse,
    KnowledgeDetailRequest,
    KnowledgeDetailResponse,
    KnowledgeListRequest,
    KnowledgeListResponse,
    KnowledgeUpdateRequest,
    KnowledgeUpdateResponse,
    MilvusTestRequest,
    MilvusTestResponse,
    MilvusTestWriteRequest,
    MilvusTestWriteResponse,
)
from engine.services.knowledge_service import knowledge_service


router = APIRouter(prefix="/v1/knowledge", tags=["knowledge"])
logger = get_logger(__name__)


@router.post("/create", response_model=KnowledgeCreateResponse)
async def create_knowledge_base(payload: KnowledgeCreateRequest) -> KnowledgeCreateResponse:
    """
    创建知识库

    :param payload: 创建请求
    :return:
    """
    trace_id = payload.task_meta.trace_id
    try:
        summary = await knowledge_service.create_database(payload)
        return KnowledgeCreateResponse(trace_id=trace_id, kb=summary)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to create knowledge base: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="创建失败")


@router.post("/delete", response_model=KnowledgeDeleteResponse)
async def delete_knowledge_base(payload: KnowledgeDeleteRequest) -> KnowledgeDeleteResponse:
    """
    删除知识库

    :param payload: 删除请求
    :return:
    """
    trace_id = payload.task_meta.trace_id
    try:
        result = await knowledge_service.delete_database(payload)
        return KnowledgeDeleteResponse(trace_id=trace_id, result=result)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to delete knowledge base: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="删除失败")


@router.post("/update", response_model=KnowledgeUpdateResponse)
async def update_knowledge_base(payload: KnowledgeUpdateRequest) -> KnowledgeUpdateResponse:
    """
    更新知识库

    :param payload: 更新请求
    :return:
    """
    trace_id = payload.task_meta.trace_id
    try:
        summary = await knowledge_service.update_database(payload)
        return KnowledgeUpdateResponse(trace_id=trace_id, kb=summary)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to update knowledge base: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新失败")


@router.post("/list", response_model=KnowledgeListResponse)
async def list_knowledge_bases(payload: KnowledgeListRequest) -> KnowledgeListResponse:
    """
    列出知识库

    :param payload: 列表请求
    :return:
    """
    trace_id = payload.task_meta.trace_id
    try:
        items, total = await knowledge_service.list_databases(payload)
        return KnowledgeListResponse(trace_id=trace_id, total=total, items=items)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to list knowledge bases: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="查询失败")


@router.post("/detail", response_model=KnowledgeDetailResponse)
async def get_knowledge_detail(payload: KnowledgeDetailRequest) -> KnowledgeDetailResponse:
    """
    获取知识库详情

    :param payload: 详情请求
    :return:
    """
    trace_id = payload.task_meta.trace_id
    try:
        summary = await knowledge_service.get_database(payload)
        return KnowledgeDetailResponse(trace_id=trace_id, kb=summary)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to get knowledge base detail: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="查询失败")


@router.post("/test_connection", response_model=MilvusTestResponse)
async def test_milvus_connection(payload: MilvusTestRequest) -> MilvusTestResponse:
    """
    测试 Milvus 连接

    :param payload: 测试请求
    :return:
    """
    trace_id = payload.task_meta.trace_id
    try:
        result = await knowledge_service.test_milvus_connection(payload)
        return MilvusTestResponse(
            trace_id=trace_id,
            status=result["status"],
            message=result["message"],
            used_uri=result["used_uri"],
            used_db=result["used_db"],
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to test Milvus connection: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="连接测试失败")


@router.post("/test_write", response_model=MilvusTestWriteResponse)
async def test_milvus_write(payload: MilvusTestWriteRequest) -> MilvusTestWriteResponse:
    """
    向指定知识库写入一条测试数据

    :param payload: 写入请求
    :return:
    """
    trace_id = payload.task_meta.trace_id
    try:
        result = await knowledge_service.test_milvus_write(payload)
        return MilvusTestWriteResponse(
            trace_id=trace_id,
            status=result["status"],
            message=result["message"],
            collection=result["collection"],
            rows=result["rows"],
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to test Milvus write: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="写入测试失败")

