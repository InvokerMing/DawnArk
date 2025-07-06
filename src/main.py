"""main.py
FastAPI entry point for receiving DingTalk callback events (HTTP mode).

When a user sends a **file** message to the bot the following flow is
executed:
1. The attachment is downloaded via *mediaId*.
2. The file is uploaded to DingDrive and a preview URL is obtained.
3. The preview URL is forwarded to the knowledge base.
4. The bot replies with the processing result.

If `PUBLIC_BASE_URL` is configured the file can also be served from the local
`/uploads` directory which is statically mounted on the FastAPI app.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .dingtalk_client import get_dingtalk_client
from .knowledge_uploader import upload_doc_url

app = FastAPI(title="DingTalk Knowledge Bot")
logger = logging.getLogger("uvicorn")
settings = get_settings()
dt_client = get_dingtalk_client()

# ---------------------------------------------------------------------------
# Static uploads directory (used when DingDrive is not available)
# ---------------------------------------------------------------------------

uploads_path = Path(__file__).resolve().parent.parent / "uploads"
uploads_path.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await dt_client.close()


# ---------------------------------------------------------------------------
# Start stream listener on startup (if callback_mode == "stream")
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def _start_stream() -> None:
    from .stream_listener import start_stream_listener  # imported lazily

    if settings.callback_mode == "stream":
        start_stream_listener()


# ---------------------------------------------------------------------------
# HTTP callback endpoint – kept for compatibility when using "http" mode
# ---------------------------------------------------------------------------

@app.post("/callback")
async def dingtalk_callback(request: Request) -> JSONResponse:  # noqa: C901
    try:
        payload: Dict[str, Any] = await request.json()
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    logger.info("回调请求: %s", payload)

    if payload.get("msgtype") != "file":
        return JSONResponse({"msg": "ignored"})

    media_id_raw = payload.get("mediaId")
    if not isinstance(media_id_raw, str):
        raise HTTPException(status_code=400, detail="mediaId missing or invalid")
    media_id: str = media_id_raw
    file_name = payload.get("fileName", "upload")

    try:
        file_bytes = await dt_client.download_file(media_id)
        doc_url = await dt_client.upload_doc_and_get_url(file_bytes, file_name)
        await upload_doc_url(doc_url, file_name)
    except Exception as exc:  # noqa: BLE001
        logger.error("文件处理失败: %s", exc)
        raise HTTPException(status_code=500, detail="processing_error") from exc

    return JSONResponse({"msg": "file_processed", "doc_url": doc_url}) 