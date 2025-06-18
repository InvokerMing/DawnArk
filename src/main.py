"""main.py
FastAPI 入口，用于接收钉钉事件回调（机器人消息）。

当用户向机器人发送文件（file 类型消息）时：
1. 先通过 mediaId 下载文件内容；
2. 上传文件到钉钉文档，获得 docUrl；
3. 将 docUrl 写入到知识库；
4. 回复用户处理结果。"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict
import os
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .dingtalk_crypto import DingTalkCrypto, DingTalkCryptoError
from .dingtalk_client import get_dingtalk_client
from .knowledge_uploader import upload_doc_url

app = FastAPI(title="DingTalk Knowledge Bot")
logger = logging.getLogger("uvicorn")
settings = get_settings()
owner_key = settings.corp_id or settings.app_key
crypto_tool = DingTalkCrypto(settings.token, settings.aes_key, owner_key)

dt_client = get_dingtalk_client()

# ------------------------------------------------------
# 若启用了本地文件直链功能（配置 PUBLIC_BASE_URL），
# 则在 /uploads 下存放文件并通过 StaticFiles 暴露。
uploads_path = Path(__file__).resolve().parent.parent / "uploads"
uploads_path.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")


@app.on_event("shutdown")
async def shutdown_event():
    await dt_client.close()


# 钉钉 HTTP 回调统一入口
@app.api_route("/dingtalk/callback", methods=["GET", "POST"])
async def dingtalk_callback(request: Request):
    query: Dict[str, str] = dict(request.query_params)
    signature = query.get("signature") or query.get("msg_signature")
    timestamp = query.get("timestamp") or query.get("timeStamp")
    nonce = query.get("nonce")

    if not (signature and timestamp and nonce):
        raise HTTPException(status_code=400, detail="缺少签名参数")

    if request.method == "GET":
        # 首次验证回调 URL
        echostr = query.get("echostr")
        try:
            plain, _ = crypto_tool.decrypt(echostr)
        except DingTalkCryptoError as e:
            logger.error("URL 验证失败: %s", e)
            raise HTTPException(status_code=400, detail="解密失败")
        # 按照官方要求，返回明文
        return JSONResponse(content=plain)

    # POST: 正常事件推送
    body = await request.json()
    encrypt_text = body.get("encrypt")
    try:
        plain_text = crypto_tool.decrypt_event(signature, timestamp, nonce, encrypt_text)
    except DingTalkCryptoError as e:
        logger.error("解密事件失败: %s", e)
        raise HTTPException(status_code=400, detail="签名或解密错误")

    event_json = json.loads(plain_text)
    event_type = event_json.get("EventType")

    # 官方在检查回调可用性时会发送 check_url
    if event_type == "check_url":
        resp = crypto_tool.encrypt_response("success")
        return JSONResponse(content=resp)

    if event_type == "event_callback":
        # 机器人普通消息
        msg = event_json.get("text", {})
        # 仅示例处理 file 消息
        if event_json.get("MsgType") == "file":
            media_id = event_json.get("MediaId")
            file_name = event_json.get("FileName", "upload")
            # 步骤 1: 下载文件
            file_bytes = await dt_client.download_file(media_id)
            # 步骤 2: 上传到钉钉文档
            doc_url = await dt_client.upload_doc_and_get_url(file_bytes, file_name)
            # 步骤 3: 追加到知识库
            await upload_doc_url(doc_url, file_name)

    # 最后必须返回加密后的 success
    resp_body = crypto_tool.encrypt_response("success")
    return JSONResponse(content=resp_body) 