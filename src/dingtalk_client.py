"""dingtalk_client.py
DingTalk 开放平台 API 的最小封装，供本项目使用。

它提供：
1. 访问令牌（access_token）获取与内存缓存；
2. 文件下载辅助函数（支持 mediaId 或官方推荐的 downloadCode）；
3. 文件上传辅助函数：先调用 media/upload，然后把文件附加到钉盘，返回可供AI助理使用的预览 URL；
4. 方便方法：根据成员姓名解析 unionId，以及根据 unionId 获取个人 spaceId。

该类 支持异步，并设计为通过 `get_dingtalk_client()` 以延迟加载的单例形式复用。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from functools import lru_cache
from typing import Optional

import httpx

from .config import get_settings, BASE_DIR

logger = logging.getLogger(__name__)
settings = get_settings()


class DingTalkClient:
    """DingTalk Open Platform 端点的高级异步抽象。

    目前仅实现了本项目所需的一小部分接口。若需扩展，只需复用内部
    `_http` 客户端，并记得在请求中附加（可能已自动刷新）的 access_token即可。
    """

    _token_cache_key = "_dingtalk_access_token"

    def __init__(self) -> None:
        # 内存中的令牌缓存（值 + 过期时间戳）
        self._token: Optional[str] = None
        self._expire_at: float = 0.0

        # 共享的 httpx.AsyncClient 实例（10 秒超时）
        self._http = httpx.AsyncClient(timeout=10)

        # 辅助缓存：人名 -> unionId / unionId -> spaceId
        self._union_cache: dict[str, str] = {}
        self._space_cache: dict[str, str] = {}

        # 防止并发写缓存
        self._lock = asyncio.Lock()

    # ---------------------------------------------------------------------
    # AccessToken 辅助方法
    # ---------------------------------------------------------------------
    async def _fetch_access_token(self) -> str:
        """向钉钉请求新的 access_token 并更新本地缓存。"""
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
        # refresh 60s before actual expiry to avoid edge cases
        self._token = token
        self._expire_at = time.time() + expires_in - 60
        return token

    async def get_access_token(self) -> str:
        """返回有效的 access_token，如有必要会自动刷新。"""
        if self._token and time.time() < self._expire_at:
            return self._token
        return await self._fetch_access_token()

    # ---------------------------------------------------------------------
    # 基础下载辅助函数
    # ---------------------------------------------------------------------
    async def get_media_download_url(self, media_id: str) -> str:
        """将 mediaId 转换为临时下载 URL。"""
        access_token = await self.get_access_token()
        return (
            "https://oapi.dingtalk.com/media/downloadFile"
            f"?access_token={access_token}&mediaId={media_id}"
        )

    async def download_file(self, media_id: str) -> bytes:
        """下载由 mediaId 指向的二进制文件。"""
        url = await self.get_media_download_url(media_id)
        resp = await self._http.get(url)
        resp.raise_for_status()
        return resp.content

    async def download_file_by_code(self, download_code: str, robot_code: str) -> bytes:
        """使用 downloadCode 流程下载附件（推荐）。"""
        token = await self.get_access_token()
        api_url = "https://api.dingtalk.com/v1.0/robot/messageFiles/download"
        headers = {"x-acs-dingtalk-access-token": token}

        # 1. exchange code for a temporary download link
        resp = await self._http.post(
            api_url,
            json={"downloadCode": download_code, "robotCode": robot_code},
            headers=headers,
        )
        resp.raise_for_status()
        download_url = resp.json().get("downloadUrl")
        if not download_url:
            raise RuntimeError(f"downloadUrl 获取失败: {resp.text}")

        # 2. actual file download
        file_resp = await self._http.get(download_url)
        file_resp.raise_for_status()
        return file_resp.content

    # ---------------------------------------------------------------------
    # 钉盘辅助函数
    # ---------------------------------------------------------------------
    async def _upload_media(self, file_bytes: bytes, filename: str) -> str:
        """通过 media/upload 接口上传 file_bytes 并返回生成的 mediaId。"""
        token = await self.get_access_token()
        url = (
            "https://oapi.dingtalk.com/media/upload"
            f"?access_token={token}&type=file"
        )
        files = {"media": (filename, file_bytes)}
        rsp = await self._http.post(url, files=files)
        data = rsp.json()
        if data.get("errcode") != 0:
            raise RuntimeError(f"media/upload 失败: {data}")
        return data["media_id"]

    async def _get_my_space_id(self) -> str:
        """获取当前用户的 spaceId（或使用 .env 中的覆盖值）。"""
        # 1. explicit override wins
        if settings.drive_space_id:
            return settings.drive_space_id

        # 2. automatic lookup requires both AGENT_ID and UNION_ID
        if not settings.agent_id:
            raise RuntimeError("请在 .env 中至少配置 AGENT_ID 或直接填写 DRIVE_SPACE_ID")
        if not settings.union_id:
            raise RuntimeError(
                "缺少 UNION_ID，且未配置 DRIVE_SPACE_ID，无法自动查询个人钉盘空间。"
            )

        token = await self.get_access_token()
        url = "https://api.dingtalk.com/v1.0/drive/spaces"
        headers = {"x-acs-dingtalk-access-token": token}
        params = {"unionId": settings.union_id, "type": "personal", "maxResults": 1}
        rsp = await self._http.get(url, params=params, headers=headers)
        if rsp.status_code != 200:
            raise RuntimeError(f"spaces 列表查询失败: {rsp.text}")

        data = rsp.json()
        space_list = data.get("spaces") or data.get("list") or []
        if not space_list:
            raise RuntimeError(f"spaces 列表为空: {rsp.text}")
        first_space = space_list[0]
        return first_space.get("spaceId") or first_space.get("space_id")

    async def _drive_add_file(self, space_id: str, media_id: str, filename: str) -> str:
        """将 mediaId 附加到钉盘并返回生成的 fileId。"""
        if not settings.agent_id:
            raise RuntimeError("请在 .env 中配置 AGENT_ID 用于钉盘接口调用")
        token = await self.get_access_token()
        url = "https://oapi.dingtalk.com/topapi/drive/file/add"
        body = {
            "agent_id": settings.agent_id,
            "space_id": space_id,
            "file_name": filename,
            "media_id": media_id,
            "overwrite": True,
        }
        rsp = await self._http.post(
            url, params={"access_token": token}, data={"request": json.dumps(body)}
        )
        data = rsp.json()
        if data.get("errcode") != 0:
            raise RuntimeError(f"file/add 失败: {data}")
        return data["result"]["file_id"]

    async def _drive_get_preview(self, space_id: str, file_id: str) -> str:
        """获取钉盘文件的网页预览 URL。"""
        if not settings.agent_id:
            raise RuntimeError("请在 .env 中配置 AGENT_ID 用于钉盘接口调用")
        token = await self.get_access_token()
        url = "https://oapi.dingtalk.com/topapi/drive/file/get_preview_info"
        body = {"agent_id": settings.agent_id, "space_id": space_id, "file_id": file_id}
        rsp = await self._http.post(
            url, params={"access_token": token}, data={"request": json.dumps(body)}
        )
        data = rsp.json()
        if data.get("errcode") != 0:
            raise RuntimeError(f"get_preview_info 失败: {data}")
        return data["result"]["preview_url"]

    # ---------------------------------------------------------------------
    # 公共辅助方法
    # ---------------------------------------------------------------------
    async def upload_doc_and_get_url(self, file_bytes: bytes, filename: str) -> str:
        """上传 file_bytes 并返回一个 HTTPS URL，使文件可以公开下载。

        优先使用钉盘进行文件托管；如果该路径不可用，则回退到本地静态目录，要求配置 `PUBLIC_BASE_URL`。
        """
        try:
            media_id = await self._upload_media(file_bytes, filename)
            space_id = await self._get_my_space_id()
            file_id = await self._drive_add_file(space_id, media_id, filename)
            return await self._drive_get_preview(space_id, file_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("钉盘上传失败，回退本地直链模式: %s", exc)

        if not settings.public_base_url:
            raise RuntimeError("钉盘上传失败，且未配置 PUBLIC_BASE_URL，无法生成文件下载链接。")

        import pathlib, uuid

        uploads_dir = pathlib.Path(BASE_DIR) / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex}_{filename}"
        file_path = uploads_dir / safe_name
        file_path.write_bytes(file_bytes)
        return f"{settings.public_base_url.rstrip('/')}/uploads/{safe_name}"

    async def close(self) -> None:
        """关闭内部的异步 HTTP 客户端。"""
        await self._http.aclose()

    # ------------------------------------------------------------------
    # 通讯录辅助方法
    # ------------------------------------------------------------------
    async def get_union_id_by_name(self, name: str) -> str:
        """将 name 解析为 unionId（带缓存）。"""
        if name in self._union_cache:
            return self._union_cache[name]

        async with self._lock:
            if name in self._union_cache:  # double-checked locking
                return self._union_cache[name]

            # step 1: fuzzy search user list
            token = await self.get_access_token()
            url_search = "https://api.dingtalk.com/v1.0/contact/users/search"
            headers = {"x-acs-dingtalk-access-token": token}
            body = {"queryWord": name, "offset": 0, "size": 10, "fullMatchField": 1}
            resp = await self._http.post(url_search, json=body, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(f"搜索用户失败: {resp.text}")
            users = resp.json().get("users", [])
            if not users:
                raise RuntimeError(f"未找到成员 {name}")
            user_id = users[0]["userId"]

            # step 2: fetch user detail to obtain unionId
            url_detail = f"https://api.dingtalk.com/v1.0/contact/users/{user_id}"
            resp2 = await self._http.get(url_detail, headers=headers)
            if resp2.status_code != 200:
                raise RuntimeError(f"获取用户详情失败: {resp2.text}")
            union_id = resp2.json().get("unionId")
            if not union_id:
                raise RuntimeError("用户详情缺少 unionId")

            self._union_cache[name] = union_id
            return union_id

    async def get_space_id_for_union(self, union_id: str) -> str:
        """返回 union_id 对应个人钉盘空间的 spaceId（带缓存）。"""
        if union_id in self._space_cache:
            return self._space_cache[union_id]

        token = await self.get_access_token()
        headers = {"x-acs-dingtalk-access-token": token}
        url = "https://api.dingtalk.com/v1.0/drive/spaces"
        params = {"unionId": union_id, "type": "personal", "maxResults": 1}
        resp = await self._http.get(url, params=params, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"查询空间失败: {resp.text}")
        spaces = resp.json().get("spaces") or []
        if not spaces:
            raise RuntimeError("个人空间列表为空")
        space_id = spaces[0]["spaceId"]
        self._space_cache[union_id] = space_id
        return space_id

    async def upload_doc_to_user_space(self, file_bytes: bytes, filename: str, union_id: str) -> str:
        """将 file_bytes 直接上传到指定用户（unionId）的个人空间。"""
        space_id = await self.get_space_id_for_union(union_id)
        media_id = await self._upload_media(file_bytes, filename)
        file_id = await self._drive_add_file(space_id, media_id, filename)
        return await self._drive_get_preview(space_id, file_id)


@lru_cache()
def get_dingtalk_client() -> DingTalkClient:
    """延迟初始化的全局 DingTalkClient 单例。"""
    return DingTalkClient() 