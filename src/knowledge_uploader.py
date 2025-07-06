"""knowledge_uploader.py
Wrapper around DingTalk *LearnKnowledge* API — uploads a document URL so that
it becomes part of the assistant knowledge base.

文档示例见：
https://dingtalk.apifox.cn/doc-3586280
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

# A single, reusable SDK client – creating it is relatively expensive.
_cfg = OpenApiConfig()
_cfg.protocol = "https"
_cfg.region_id = "central"
_assistant_client = AssistantClient(_cfg)


async def upload_doc_url(doc_url: str, title: str) -> bool:
    """Let the assistant learn a document given by *doc_url*.

    Returns ``True`` on success, ``False`` otherwise.
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