"""dingtalk_client.py
A minimal wrapper around DingTalk Open Platform APIs used in this project.

It offers:
1. Access-token retrieval with in-memory caching.
2. File download helpers (by mediaId or the officially recommended downloadCode).
3. File upload helpers that first call media/upload and then attach the file
   to DingDrive, returning a preview URL that can be consumed by the assistant.
4. Convenience methods for resolving user names to unionId and obtaining the
   personal spaceId associated with a unionId.

The class is **async-friendly** and designed to be reused as a lazily-loaded
singleton via `get_dingtalk_client()`.
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
    """High-level async abstraction of DingTalk Open Platform endpoints.

    The implementation purposefully covers only the subset of endpoints that
    the current project requires.  Adding new methods is straightforward—just
    reuse the internal `_http` client and remember to tack the (possibly
    refreshed) access token onto the request.
    """

    _token_cache_key = "_dingtalk_access_token"

    def __init__(self) -> None:
        # in-memory token cache (value + expiry timestamp)
        self._token: Optional[str] = None
        self._expire_at: float = 0.0

        # shared httpx.AsyncClient instance (10-second timeout)
        self._http = httpx.AsyncClient(timeout=10)

        # auxiliary caches:  human-name -> unionId / unionId -> spaceId
        self._union_cache: dict[str, str] = {}
        self._space_cache: dict[str, str] = {}

        # guards concurrent cache fills
        self._lock = asyncio.Lock()

    # ---------------------------------------------------------------------
    # Access token helpers
    # ---------------------------------------------------------------------
    async def _fetch_access_token(self) -> str:
        """Query DingTalk for a fresh access token and update local cache."""
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
        """Return a valid access token, refreshing it if necessary."""
        if self._token and time.time() < self._expire_at:
            return self._token
        return await self._fetch_access_token()

    # ---------------------------------------------------------------------
    # Basic download helpers
    # ---------------------------------------------------------------------
    async def get_media_download_url(self, media_id: str) -> str:
        """Convert a *mediaId* into a temporary download URL."""
        access_token = await self.get_access_token()
        return (
            "https://oapi.dingtalk.com/media/downloadFile"
            f"?access_token={access_token}&mediaId={media_id}"
        )

    async def download_file(self, media_id: str) -> bytes:
        """Download the binary payload referenced by *mediaId*."""
        url = await self.get_media_download_url(media_id)
        resp = await self._http.get(url)
        resp.raise_for_status()
        return resp.content

    async def download_file_by_code(self, download_code: str, robot_code: str) -> bytes:
        """Download an attachment using the *downloadCode* flow (preferred)."""
        token = await self.get_access_token()
        api_url = "https://api.dingtalk.com/v1.0/robot/messageFiles/download"
        headers = {"x-acs-dingtalk-access-token": token}

        # 1️⃣ exchange code for a temporary download link
        resp = await self._http.post(
            api_url,
            json={"downloadCode": download_code, "robotCode": robot_code},
            headers=headers,
        )
        resp.raise_for_status()
        download_url = resp.json().get("downloadUrl")
        if not download_url:
            raise RuntimeError(f"downloadUrl 获取失败: {resp.text}")

        # 2️⃣ actual file download
        file_resp = await self._http.get(download_url)
        file_resp.raise_for_status()
        return file_resp.content

    # ---------------------------------------------------------------------
    # DingDrive helpers
    # ---------------------------------------------------------------------
    async def _upload_media(self, file_bytes: bytes, filename: str) -> str:
        """Upload *file_bytes* via media/upload and return the generated mediaId."""
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
        """Return the spaceId for the current user (or .env override)."""
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
        """Attach a *mediaId* to DingDrive and return the resulting fileId."""
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
        """Return the web preview URL for a DingDrive file."""
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
    # Public helpers (used by other modules)
    # ---------------------------------------------------------------------
    async def upload_doc_and_get_url(self, file_bytes: bytes, filename: str) -> str:
        """Upload *file_bytes* and return an HTTPS URL to make it publicly downloadable.

        The function prioritises DingDrive for production-quality hosting.  If
        that path is not viable (e.g. missing credentials in development) it
        falls back to a local static directory that FastAPI exposes via
        `StaticFiles` *provided* that `PUBLIC_BASE_URL` is configured.
        """
        try:
            media_id = await self._upload_media(file_bytes, filename)
            space_id = await self._get_my_space_id()
            file_id = await self._drive_add_file(space_id, media_id, filename)
            return await self._drive_get_preview(space_id, file_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("钉盘上传失败，回退本地直链模式: %s", exc)

        # fallback: local static hosting
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
        """Close the internal async http client."""
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Address-book helpers
    # ------------------------------------------------------------------
    async def get_union_id_by_name(self, name: str) -> str:
        """Resolve *name* to unionId (cached)."""
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
        """Return the DingDrive personal spaceId for *union_id* (cached)."""
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
        """Upload *file_bytes* directly into the personal space of *union_id*."""
        space_id = await self.get_space_id_for_union(union_id)
        media_id = await self._upload_media(file_bytes, filename)
        file_id = await self._drive_add_file(space_id, media_id, filename)
        return await self._drive_get_preview(space_id, file_id)


@lru_cache()
def get_dingtalk_client() -> DingTalkClient:
    """Lazily-initialised process-wide DingTalkClient singleton."""
    return DingTalkClient() 