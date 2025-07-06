"""config.py
Centralised environment-variable configuration using a lightweight
Settings class.  All modules should retrieve the singleton instance via
`get_settings()` to avoid repeated parsing.
"""

import os
from functools import lru_cache
from dotenv import load_dotenv


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load a sibling .env file if present.  Variables already defined in the
# shell take precedence (override=False).
load_dotenv(os.path.join(BASE_DIR, ".env"), override=False)


class Settings:
    """Container for project-wide configuration values."""

    # DingTalk App
    app_key: str = os.getenv("DINGTALK_APP_KEY", "")
    app_secret: str = os.getenv("DINGTALK_APP_SECRET", "")
    assistant_id: str = os.getenv("ASSISTANT_ID", "")

    # HTTP server
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))

    # Public base URL used for static downloads
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "")

    # DingDrive (optional)
    drive_space_id: str | None = os.getenv("DRIVE_SPACE_ID")
    agent_id: str | None = os.getenv("AGENT_ID")
    # current operator
    union_id: str | None = os.getenv("UNION_ID")

    # Callback mode: http / stream.  Defaults to http
    callback_mode: str = os.getenv("CALLBACK_MODE", "http").lower()


@lru_cache()
def get_settings() -> Settings:
    """Return a cached `Settings` instance (process-wide singleton)."""
    return Settings()