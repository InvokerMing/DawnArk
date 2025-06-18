import os
from functools import lru_cache
from dotenv import load_dotenv


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 尝试加载同级目录的 .env 文件；用户可自行复制 env.example
load_dotenv(os.path.join(BASE_DIR, '.env'), override=False)


class Settings:
    """读取环境变量配置"""

    # 钉钉基础配置
    app_key: str = os.getenv('DINGTALK_APP_KEY', '')
    app_secret: str = os.getenv('DINGTALK_APP_SECRET', '')
    token: str = os.getenv('DINGTALK_TOKEN', '')
    aes_key: str = os.getenv('DINGTALK_AES_KEY', '')
    corp_id: str = os.getenv('DINGTALK_CORP_ID', '')
    assistant_id: str = os.getenv('ASSISTANT_ID', '')

    # 服务端口
    host: str = os.getenv('HOST', '0.0.0.0')
    port: int = int(os.getenv('PORT', '8000'))

    # 供演示的公网域名（如配置，则文件保存到本地 uploads 目录并生成直链）
    public_base_url: str = os.getenv('PUBLIC_BASE_URL', '')


@lru_cache()
def get_settings() -> Settings:
    """缓存 Settings 防止重复解析"""
    return Settings() 