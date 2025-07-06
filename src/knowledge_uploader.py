"""
knowledge_uploader.py
DingTalk LearnKnowledge API 的轻量封装 —— 上传文档 URL，使其成为AI助理知识库的一部分。
"""

from __future__ import annotations

import logging

from alibabacloud_dingtalk.assistant_1_0.client import Client as AssistantClient
from alibabacloud_tea_openapi.models import Config as OpenApiConfig
from alibabacloud_dingtalk.assistant_1_0 import models as assistant_models
from alibabacloud_tea_util.models import RuntimeOptions

from .config import get_settings
from .dingtalk_client import get_dingtalk_client

logger = logging.getLogger(__name__)
settings = get_settings()

_cfg = OpenApiConfig()
_cfg.protocol = "https"
_cfg.region_id = "central"
_assistant_client = AssistantClient(_cfg)


async def upload_doc_url(doc_url: str, title: str) -> bool:
    """让AI助理学习由 doc_url 指定的文档。

    成功返回 ``True``，失败返回 ``False``。
    """

    if not settings.assistant_id:
        logger.warning("未配置 ASSISTANT_ID，跳过 LearnKnowledge 调用")
        return False

    access_token = await get_dingtalk_client().get_access_token()

    headers = assistant_models.LearnKnowledgeHeaders()
    headers.x_acs_dingtalk_access_token = access_token

    logger.info("上传到知识库 doc_url=%s", doc_url)

    req = assistant_models.LearnKnowledgeRequest(
        assistant_id=settings.assistant_id,
        doc_url=doc_url,
    )

    try:
        _assistant_client.learn_knowledge_with_options(req, headers, RuntimeOptions())
        logger.info("AI 助理已学习文档: %s", title)
        return True
    except Exception as err:  # noqa: BLE001
        logger.error("LearnKnowledge 调用失败: %s", err)
        return False 