"""dingtalk_client.py
封装获取 access_token、下载媒体文件、上传钉钉文档等常用操作。"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from functools import lru_cache
from typing import Optional

import httpx

from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class DingTalkClient:
    """简易钉钉开放平台 API 封装（仅用到少量接口）"""

    _token_cache_key = "_dingtalk_access_token"

    def __init__(self):
        self._token: Optional[str] = None
        self._expire_at: float = 0.0
        self._http = httpx.AsyncClient(timeout=10)

    # ---------------------------------------------------------------------
    async def _fetch_access_token(self) -> str:
        url = "https://oapi.dingtalk.com/gettoken"
        params = {
            "appkey": settings.app_key,
            "appsecret": settings.app_secret,
        }
        resp = await self._http.get(url, params=params)
        data = resp.json()
        if data.get("errcode") != 0:
            raise RuntimeError(f"获取 access_token 失败: {data}")
        token = data["access_token"]
        expires_in = int(data.get("expires_in", 7200))
        self._token = token
        self._expire_at = time.time() + expires_in - 60  # 提前一分钟过期
        return token

    async def get_access_token(self) -> str:
        if self._token and time.time() < self._expire_at:
            return self._token
        return await self._fetch_access_token()

    # ---------------------------------------------------------------------
    async def get_media_download_url(self, media_id: str) -> str:
        """通过 mediaId 获取文件下载地址 (示例使用机器人媒体文件下载接口)"""
        access_token = await self.get_access_token()
        url = f"https://oapi.dingtalk.com/media/downloadFile?access_token={access_token}&mediaId={media_id}"
        # 该接口返回 redirect，可直接返回 URL 供下载
        return url

    async def download_file(self, media_id: str) -> bytes:
        url = await self.get_media_download_url(media_id)
        resp = await self._http.get(url)
        resp.raise_for_status()
        return resp.content

    # ---------------------------------------------------------------------
    async def upload_doc_and_get_url(self, file_bytes: bytes, filename: str) -> str:
        """返回可供 AI 助理学习的文件 HTTPS 链接。

        为了方便本地/演示环境快速跑通流程：
        1. 若在 .env 中配置了 PUBLIC_BASE_URL（例如 https://demo.example.com ），
           则直接把文件保存到 `uploads/` 目录并生成直链：
               <PUBLIC_BASE_URL>/uploads/<uuid_filename>
           FastAPI 会自动挂载 StaticFiles 提供下载。

        2. 若未配置，则退回旧实现——调用 `media/upload` 拿 mediaId，
           并返回 `dingtalk://` 协议链接（仅在真机内可下载）。

        生产环境推荐调用钉钉文档/钉盘正式接口以获取稳定的 HTTPS docUrl。"""

        # -- 方案 1: 本地直链 --
        if settings.public_base_url:
            import os
            import uuid
            from pathlib import Path

            uploads_dir = Path(__file__).resolve().parent.parent / "uploads"
            uploads_dir.mkdir(parents=True, exist_ok=True)

            suffix = Path(filename).suffix or ""
            new_name = f"{uuid.uuid4().hex}{suffix}"
            file_path = uploads_dir / new_name
            file_path.write_bytes(file_bytes)

            doc_url = f"{settings.public_base_url.rstrip('/')}/uploads/{new_name}"
            logger.debug("本地文件已保存至 %s，对外链接: %s", file_path, doc_url)
            return doc_url

        # -- 方案 2: 回退 mediaId --
        access_token = await self.get_access_token()
        upload_url = f"https://oapi.dingtalk.com/media/upload?access_token={access_token}&type=file"
        files = {"media": (filename, file_bytes)}
        resp = await self._http.post(upload_url, files=files)
        data = resp.json()
        if data.get("errcode") != 0:
            raise RuntimeError(f"上传文件失败: {data}")
        media_id = data["media_id"]
        doc_url = f"dingtalk://dingtalkclient/action/download_file?mediaId={media_id}"
        return doc_url

    # ---------------------------------------------------------------------
    async def close(self):
        await self._http.aclose()


# 单例（懒加载）
@lru_cache()
def get_dingtalk_client() -> DingTalkClient:
    return DingTalkClient() 