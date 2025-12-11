from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from engine.logging_utils import get_logger, sanitize_log_message


@dataclass
class UploadResult:
    """上传结果"""

    url: str


class UploadClient:
    """通用 HTTP 上传客户端"""

    def __init__(
        self,
        upload_url: str,
        file_field: str = "file",
        extra_headers: Optional[Dict[str, str]] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        self.upload_url = upload_url
        self.file_field = file_field
        self.extra_headers = extra_headers or {}
        self.logger = get_logger(trace_id)

        if not self.upload_url:
            raise ValueError("缺少上传接口 URL（FILE_UPLOAD_URL）")

    async def upload_bytes(
        self,
        filename: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> UploadResult:
        """上传字节内容，返回可访问 URL"""
        files = {self.file_field: (filename, data, content_type)}
        headers = self.extra_headers

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(self.upload_url, files=files, headers=headers)
                resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            message = sanitize_log_message(str(exc))
            self.logger.error(f"上传失败: {message}")
            raise

        try:
            payload: Dict[str, Any] = resp.json()
        except Exception as exc:  # noqa: BLE001
            self.logger.error(f"上传响应非 JSON: {sanitize_log_message(str(exc))}")
            raise ValueError("上传响应不是 JSON") from exc

        url = self._extract_url(payload)
        return UploadResult(url=url)

    def _extract_url(self, payload: Dict[str, Any]) -> str:
        """从响应中提取 URL，默认查找 url 字段"""
        if "url" in payload and isinstance(payload["url"], str):
            return payload["url"]
        # 兼容 data.url
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("url"), str):
            return data["url"]
        self.logger.error(f"上传响应缺少 url 字段: {sanitize_log_message(json.dumps(payload))}")
        raise ValueError("上传响应中未找到 url 字段")


