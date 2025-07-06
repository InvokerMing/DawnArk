"""
config.py
集中管理环境变量的配置模块，使用轻量级 Settings 类封装。
所有模块都应通过 `get_settings()` 获取单例实例，避免重复解析。
"""

import os
from functools import lru_cache
from dotenv import load_dotenv


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 如果存在同级 .env 文件则加载；已在 shell 中定义的变量具有更高优先级（override=False）。
load_dotenv(os.path.join(BASE_DIR, ".env"), override=False)


class Settings:
    """项目级配置值的容器。"""

    # 钉钉应用
    app_key: str = os.getenv("DINGTALK_APP_KEY", "")
    app_secret: str = os.getenv("DINGTALK_APP_SECRET", "")
    assistant_id: str = os.getenv("ASSISTANT_ID", "")

    # HTTP 服务器
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))

    # 用于静态下载的公共基础 URL
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "")

    # 钉盘
    drive_space_id: str | None = os.getenv("DRIVE_SPACE_ID")
    agent_id: str | None = os.getenv("AGENT_ID")

    # 当前操作人
    union_id: str | None = os.getenv("UNION_ID")



@lru_cache()
def get_settings() -> Settings:
    """返回缓存的 `Settings` 实例（进程级单例）。"""
    return Settings()