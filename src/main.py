"""
main.py
FastAPI 入口，用于接收钉钉回调事件（HTTP 模式）。

当用户向机器人发送 文件 消息时，会执行以下流程：
1. 使用 mediaId 下载附件；
2. 将文件上传到钉盘并获取预览 URL；
3. 将该预览 URL 转发到知识库；
4. 机器人把处理结果回复给用户。

"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .dingtalk_client import get_dingtalk_client

app = FastAPI(title="DingTalk Knowledge Bot")
logger = logging.getLogger("uvicorn")
settings = get_settings()
dt_client = get_dingtalk_client()

# ---------------------------------------------------------------------------
# 静态上传目录（在钉盘不可用时使用，未测试）
# ---------------------------------------------------------------------------

uploads_path = Path(__file__).resolve().parent.parent / "uploads"
uploads_path.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await dt_client.close()


# ---------------------------------------------------------------------------
# 应用启动时启动 Stream 监听器
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def _start_stream() -> None:
    from .stream_listener import start_stream_listener  # imported lazily

    start_stream_listener()