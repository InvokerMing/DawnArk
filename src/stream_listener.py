"""stream_listener.py
基于 dingtalk-stream SDK 的异步事件监听器。

监听器只注册了一个 `FileBotHandler`，它关注两种消息类型：
1. file – 下载附件 → 上传钉盘 → 将预览 URL 写入助手知识库；
2. text – 回复成功确认。

`start_stream_listener()` 在应用启动时由 `main.py` 导入，
在后台线程中运行 SDK 客户端，从而允许 FastAPI 继续处理 HTTP 请求。
"""

from __future__ import annotations

import logging
import threading

import dingtalk_stream
from dingtalk_stream import AckMessage, CallbackMessage
from dingtalk_stream.chatbot import ChatbotMessage, ChatbotHandler

from .config import get_settings
from .dingtalk_client import get_dingtalk_client
from .knowledge_uploader import upload_doc_url


# ---------------------------------------------------------------------------
# 日志设置 —— 保持各模块输出格式一致
# ---------------------------------------------------------------------------

def _setup_logger() -> logging.Logger:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(name)-8s %(levelname)-8s %(message)s [%(filename)s:%(lineno)d]"
        )
    )
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    logging.getLogger("dingtalk_stream").setLevel(logging.INFO)
    return root_logger


logger = _setup_logger()
settings = get_settings()


class FileBotHandler(ChatbotHandler):
    """处理钉钉 Stream 推送的 file 与 text 消息。"""

    async def process(self, callback: CallbackMessage):  # type: ignore[override]
        logger.info("收到 Stream 原始消息: %s", callback.data)

        message = ChatbotMessage.from_dict(callback.data)
        msgtype = message.message_type  # type: ignore[attr-defined]

        # --------------------------------------------------------------
        # 文件消息 – 下载 → 上传 → 学习
        # --------------------------------------------------------------
        if msgtype == "file":
            content = callback.data.get("content", {})  # type: ignore[index]
            download_code: str | None = content.get("downloadCode")  # type: ignore[assignment]
            file_name: str = content.get("fileName", "upload")

            if not download_code:
                logger.warning("文件消息缺少 downloadCode，忽略: %s", callback.data)
                return AckMessage.STATUS_OK, "missing_download_code"

            logger.info("处理文件消息: %s (code=%s)", file_name, download_code)

            dt_client = get_dingtalk_client()
            robot_code = message.robot_code or settings.app_key  # fallback

            try:
                file_bytes = await dt_client.download_file_by_code(download_code, robot_code)
            except Exception as exc:  # noqa: BLE001
                logger.error("下载文件失败: %s", exc)
                return AckMessage.STATUS_SYSTEM_EXCEPTION, "download_error"

            try:
                sender_name: str = callback.data.get("senderNick", "")  # type: ignore[index]
                union_id = await dt_client.get_union_id_by_name(sender_name.strip())
                doc_url = await dt_client.upload_doc_to_user_space(file_bytes, file_name, union_id)
                await upload_doc_url(doc_url, file_name)
            except Exception as exc:  # noqa: BLE001
                logger.error("上传并写入知识库失败: %s", exc)
                return AckMessage.STATUS_SYSTEM_EXCEPTION, "upload_error"

            self.reply_text("文件已处理", message)
            return AckMessage.STATUS_OK, "file_processed"

        # --------------------------------------------------------------
        # 文本消息 – 简单回显确认
        # --------------------------------------------------------------
        if msgtype == "text":
            text = message.text.content.strip()  # type: ignore[attr-defined]
            logger.info("收到文本消息内容: %s", text)
            self.reply_text("成功", message)
            return AckMessage.STATUS_OK, "text_processed"

        # 未处理的消息类型
        logger.info("忽略的消息类型: %s", msgtype)
        return AckMessage.STATUS_OK, "ignored"


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------

def start_stream_listener() -> None:
    """在后台线程中启动 DingTalk 流式客户端。"""

    credential = dingtalk_stream.Credential(settings.app_key, settings.app_secret)
    client = dingtalk_stream.DingTalkStreamClient(credential)

    client.register_callback_handler(ChatbotMessage.TOPIC, FileBotHandler())

    thread = threading.Thread(target=client.start_forever, daemon=True)
    thread.start()
    logger.info("DingTalk Stream 客户端已启动，等待事件推送…") 