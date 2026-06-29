"""应用配置 —— 从 .env 或环境变量读取."""

from pathlib import Path

from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "agent_system.db"


def resolve_database_url(url: str) -> str:
    """将 sqlite:///./xxx 解析为基于项目根目录的绝对路径，避免 cwd 不同导致多份库。"""
    relative_prefix = "sqlite:///./"
    if url.startswith(relative_prefix):
        rel = url[len(relative_prefix) :]
        abs_path = (PROJECT_ROOT / rel).resolve()
        return f"sqlite:///{abs_path.as_posix()}"
    if url == "sqlite:///./agent_system.db" or url.endswith("/agent_system.db"):
        return f"sqlite:///{DEFAULT_SQLITE_PATH.resolve().as_posix()}"
    return url


class Settings(BaseSettings):
    # ── Database ──
    # 开发默认 SQLite；生产可改为 postgresql://... 并 pip install psycopg2-binary
    database_url: str = f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"

    # ── JWT ──
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # ── CORS ──
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"

    # ── LLM ──
    llm_api_key: str = ""
    deepseek_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
settings.database_url = resolve_database_url(settings.database_url)
