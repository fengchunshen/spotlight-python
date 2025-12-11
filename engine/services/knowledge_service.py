import asyncio
import contextlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from engine.config import config
from engine.logging_utils import get_logger
from engine.schemas.knowledge import (
    KnowledgeCreateRequest,
    KnowledgeDeleteRequest,
    KnowledgeDetailRequest,
    KnowledgeListRequest,
    KnowledgeSummary,
    KnowledgeUpdateRequest,
    MilvusTestRequest,
    MilvusTestWriteRequest,
)
from engine.utils.knowledge.file_parser import chunk_file, chunk_text, process_file_to_markdown
from engine.utils.storage.upload_client import UploadClient
try:
    from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, db, utility  # type: ignore
except Exception:  # noqa: BLE001
    connections = None
    db = None
    Collection = None
    CollectionSchema = None
    FieldSchema = None
    DataType = None
    utility = None


logger = get_logger(__name__)


class KnowledgeService:
    """知识库管理服务"""

    def __init__(self, work_dir: str | Path):
        """
        初始化知识库服务

        :param work_dir: 元数据存储路径
        :return:
        """
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.meta_file = self.work_dir / "global_metadata.json"
        self._lock = asyncio.Lock()
        self._metadata: dict[str, Any] = {"databases": {}}

        self._load_metadata()

    def _load_metadata(self) -> None:
        """加载元数据"""
        if not self.meta_file.exists():
            self._metadata = {"databases": {}}
            return

        try:
            self._metadata = json.loads(self.meta_file.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to load knowledge metadata: {exc}")
            self._metadata = {"databases": {}}

    def _save_metadata(self) -> None:
        """保存元数据"""
        temp_file = self.meta_file.with_suffix(".tmp")
        self.meta_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file.write_text(json.dumps(self._metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_file.replace(self.meta_file)

    @staticmethod
    def _now_iso() -> str:
        """返回当前 UTC ISO 字符串"""
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_visibility(value: str | None) -> str:
        """标准化可见性"""
        if not value:
            return "private"
        normalized = value.lower()
        if normalized not in {"private", "public"}:
            return "private"
        return normalized

    def _ensure_milvus_type(self, kb_type: str) -> None:
        """校验知识库类型仅支持 milvus"""
        if kb_type != "milvus":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="仅支持 milvus 知识库类型",
            )

    def _build_summary(self, kb_id: str, record: dict[str, Any]) -> KnowledgeSummary:
        """构造知识库摘要"""
        return KnowledgeSummary(
            kb_id=kb_id,
            kb_name=record.get("kb_name", ""),
            description=record.get("description"),
            kb_type=record.get("kb_type", "milvus"),
            visibility=record.get("visibility", "private"),
            owner=record.get("owner", ""),
            tenant=record.get("tenant", ""),
            embedding_model=record.get("embedding_model", ""),
            created_at=record.get("created_at", ""),
        )

    def _get_record(self, kb_id: str) -> dict[str, Any]:
        """获取记录"""
        record = self._metadata.get("databases", {}).get(kb_id)
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
        return record

    def _parse_upload_headers(self) -> dict[str, str]:
        """解析上传接口头信息"""
        if not config.FILE_UPLOAD_HEADERS:
            return {}
        try:
            headers = json.loads(config.FILE_UPLOAD_HEADERS)
            if isinstance(headers, dict):
                return {str(k): str(v) for k, v in headers.items()}
        except Exception:
            pass
        return {}

    async def create_database(self, payload: KnowledgeCreateRequest) -> KnowledgeSummary:
        """
        创建知识库

        :param payload: 创建请求模型
        :return:
        """
        kb_type = "milvus"
        self._ensure_milvus_type(kb_type)

        kb_id = payload.kb_id or f"{config.MILVUS_COLLECTION_PREFIX}{uuid4().hex[:12]}"
        visibility = self._normalize_visibility(payload.visibility)

        async with self._lock:
            if kb_id in self._metadata["databases"]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="知识库已存在")

            self._metadata["databases"][kb_id] = {
                "kb_name": payload.kb_name,
                "description": payload.description,
                "kb_type": kb_type,
                "visibility": visibility,
                "owner": payload.owner,
                "tenant": payload.tenant,
                "embedding_model": payload.embedding_model,
                "vector_store_config": payload.vector_store_config or {},
                "created_at": self._now_iso(),
            }
            self._save_metadata()

        record = self._metadata["databases"][kb_id]
        return self._build_summary(kb_id, record)

    async def delete_database(self, payload: KnowledgeDeleteRequest) -> str:
        """
        删除知识库

        :param payload: 删除请求
        :return:
        """
        kb_id = payload.kb_id
        async with self._lock:
            if kb_id not in self._metadata.get("databases", {}):
                return "success"

            self._metadata["databases"].pop(kb_id, None)
            self._save_metadata()

        return "success"

    async def update_database(self, payload: KnowledgeUpdateRequest) -> KnowledgeSummary:
        """
        更新知识库

        :param payload: 更新请求
        :return:
        """
        async with self._lock:
            record = self._get_record(payload.kb_id)

            if payload.kb_name:
                record["kb_name"] = payload.kb_name
            if payload.description is not None:
                record["description"] = payload.description
            if payload.visibility:
                record["visibility"] = self._normalize_visibility(payload.visibility)
            if payload.embedding_model:
                record["embedding_model"] = payload.embedding_model
            if payload.vector_store_config is not None:
                record["vector_store_config"] = payload.vector_store_config

            self._metadata["databases"][payload.kb_id] = record
            self._save_metadata()

        return self._build_summary(payload.kb_id, record)

    async def list_databases(self, payload: KnowledgeListRequest) -> tuple[list[KnowledgeSummary], int]:
        """
        列出知识库

        :param payload: 查询请求
        :return:
        """
        records = list(self._metadata.get("databases", {}).items())

        if payload.owner:
            records = [(kb_id, rec) for kb_id, rec in records if rec.get("owner") == payload.owner]
        if payload.tenant:
            records = [(kb_id, rec) for kb_id, rec in records if rec.get("tenant") == payload.tenant]

        total = len(records)
        start = max((payload.page - 1) * payload.size, 0)
        end = start + payload.size
        items = [self._build_summary(kb_id, rec) for kb_id, rec in records[start:end]]
        return items, total

    async def get_database(self, payload: KnowledgeDetailRequest) -> KnowledgeSummary:
        """
        获取知识库详情

        :param payload: 详情请求
        :return:
        """
        record = self._get_record(payload.kb_id)
        return self._build_summary(payload.kb_id, record)

    async def test_milvus_connection(self, payload: MilvusTestRequest) -> dict[str, str]:
        """
        测试 Milvus 连接

        :param payload: 测试请求
        :return:
        """
        alias = f"milvus_test_{uuid4().hex[:6]}"
        uri = payload.milvus_uri or config.MILVUS_URI
        token = payload.milvus_token or config.MILVUS_TOKEN
        target_db = payload.milvus_db or config.MILVUS_DB

        if connections is None or db is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="pymilvus 未安装",
            )

        try:
            connections.connect(alias=alias, uri=uri, token=token)
            available_dbs = db.list_database(using=alias)
            if target_db and target_db not in available_dbs:
                db.create_database(target_db, using=alias)
            db.using_database(target_db, using=alias)
            return {
                "status": "ok",
                "message": "连接成功",
                "used_uri": uri,
                "used_db": target_db,
            }
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            error_type = type(exc).__name__
            logger.warning(f"Milvus 连接测试失败: {error_type}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"无法连接 Milvus（{error_type}）",
            )
        finally:
            with contextlib.suppress(Exception):
                connections.disconnect(alias)

    async def test_milvus_write(self, payload: MilvusTestWriteRequest) -> dict[str, Any]:
        """
        在指定知识库集合写入一条测试数据

        :param payload: 写入请求
        :return:
        """
        if (
            connections is None
            or db is None
            or Collection is None
            or CollectionSchema is None
            or FieldSchema is None
            or DataType is None
            or utility is None
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="pymilvus 未安装",
            )

        record = self._get_record(payload.kb_id)
        alias = f"milvus_write_{uuid4().hex[:6]}"
        uri = config.MILVUS_URI
        token = config.MILVUS_TOKEN
        target_db = config.MILVUS_DB
        collection_name = payload.kb_id
        embedding_dim = max(1, payload.embedding_dim)
        content = payload.content or "milvus test data"

        try:
            connections.connect(alias=alias, uri=uri, token=token)
            if target_db not in db.list_database(using=alias):
                db.create_database(target_db, using=alias)
            db.using_database(target_db, using=alias)

            from random import random

            fields = [
                FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, auto_id=False, max_length=64),
                FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=2048),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=embedding_dim),
            ]

            if connections.get_connection_addr(alias).get("db_name") != target_db:
                db.using_database(target_db, using=alias)

            if utility.has_collection(collection_name, using=alias):
                collection = Collection(name=collection_name, using=alias)
            else:
                schema = CollectionSchema(fields=fields, description=f"Test collection for {collection_name}")
                collection = Collection(name=collection_name, schema=schema, using=alias)
                index_params = {"metric_type": "COSINE", "index_type": "IVF_FLAT", "params": {"nlist": 1024}}
                collection.create_index("embedding", index_params)

            test_id = f"test_{uuid4().hex[:12]}"
            vector = [random() for _ in range(embedding_dim)]
            # pymilvus insert 期望列式数据，顺序与 schema 对齐
            entities = [
                [test_id],      # id
                [content],      # content
                [vector],       # embedding
            ]

            collection.insert(entities, timeout=30)
            collection.flush()

            return {
                "status": "ok",
                "message": "写入成功",
                "collection": collection_name,
                "rows": 1,
            }
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            error_type = type(exc).__name__
            logger.warning(f"Milvus 写入测试失败: {error_type}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Milvus 写入失败（{error_type}）",
            )
        finally:
            with contextlib.suppress(Exception):
                connections.disconnect(alias)

    def _build_upload_client(self, trace_id: str | None = None) -> UploadClient:
        """创建上传客户端"""
        headers = self._parse_upload_headers()
        return UploadClient(
            upload_url=config.FILE_UPLOAD_URL,
            file_field=config.FILE_UPLOAD_FIELD,
            extra_headers=headers,
            trace_id=trace_id,
        )

    async def convert_file_to_markdown(
        self,
        file_path: str,
        params: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> str:
        """
        将文件转换为 Markdown 文本

        :param file_path: 文件路径或 HTTP(S) URL
        :param params: 处理参数（db_id/chunk_size/enable_ocr 等）
        :param trace_id: 链路追踪 ID
        :return:
        """
        params = params or {}
        logger = get_logger(trace_id)

        try:
            upload_client = self._build_upload_client(trace_id)
            return await process_file_to_markdown(
                file_path=file_path,
                params=params,
                uploader=upload_client,
                trace_id=trace_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error(f"转换文件失败: {exc.__class__.__name__}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="文件解析失败") from exc

    async def chunk_text_content(
        self,
        text: str,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
    ) -> list[dict[str, Any]]:
        """
        按配置切分文本

        :param text: 待切分文本
        :param chunk_size: 块大小
        :param chunk_overlap: 重叠大小
        :return:
        """
        return chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    async def chunk_file_content(
        self,
        file_path: str,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        trace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        读取文件并切分

        :param file_path: 文件路径
        :param chunk_size: 块大小
        :param chunk_overlap: 重叠大小
        :param trace_id: 链路追踪 ID
        :return:
        """
        try:
            return await chunk_file(file_path, chunk_size=chunk_size, chunk_overlap=chunk_overlap, trace_id=trace_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            logger = get_logger(trace_id)
            logger.error(f"切分文件失败: {exc.__class__.__name__}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="文件切分失败") from exc


knowledge_service = KnowledgeService(config.KNOWLEDGE_WORK_DIR)

