"""knowledge_uploader.py
调用 AI 助理 LearnKnowledge 接口，将 docUrl 添加到助理知识库。

文档示例见：
https://dingtalk.apifox.cn/doc-3586280
"""

from __future__ import annotations

import logging

from alibabacloud_dingtalk.assistant_1_0.client import (
    Client as AssistantClient,
)
from alibabacloud_tea_openapi.models import Config as OpenApiConfig
from alibabacloud_dingtalk.assistant_1_0 import models as assistant_models
from alibabacloud_tea_util.models import RuntimeOptions

from .config import get_settings
from .dingtalk_client import get_dingtalk_client

logger = logging.getLogger(__name__)
settings = get_settings()


# 初始化钉钉 SDK Client（全局复用）
_cfg = OpenApiConfig()
_cfg.protocol = "https"
_cfg.region_id = "central"
_assistant_client = AssistantClient(_cfg)


async def upload_doc_url(doc_url: str, title: str) -> bool:
    """调用 LearnKnowledge，将 doc_url 收录到 AI 助理知识库"""

    if not settings.assistant_id:
        logger.warning("未配置 ASSISTANT_ID，跳过 LearnKnowledge 调用")
        return False

    # 获取 access_token
    access_token = await get_dingtalk_client().get_access_token()

    headers = assistant_models.LearnKnowledgeHeaders()
    headers.x_acs_dingtalk_access_token = access_token

    req = assistant_models.LearnKnowledgeRequest(
        assistant_id=settings.assistant_id,
        doc_url=doc_url,
    )

    try:
        _assistant_client.learn_knowledge_with_options(
            req, headers, RuntimeOptions()
        )
        logger.info("AI 助理已学习文档: %s", title)
        return True
    except Exception as err:  # SDK 报错
        logger.error("LearnKnowledge 调用失败: %s", err)
        return False 