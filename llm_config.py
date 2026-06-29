"""统一 LLM API 配置：OPENAI_* 环境变量，兼容 OpenAI / DeepSeek 等兼容端点。"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# 固定从项目根目录加载 .env，避免工作目录不同导致读不到配置
_PROJECT_ROOT = Path(__file__).resolve().parent
_ENV_FILE = _PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=_ENV_FILE, override=True)

# DeepSeek 默认配置（当 .env 未设置 OPENAI_BASE_URL 时作参考，不强制）
DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TEMPERATURE = 0.2

_PLACEHOLDER_KEYS = {
    "",
    "your_api_key_here",
    "your_deepseek_api_key_here",
    "sk-xxx",
}


def _normalize_base_url(url: str) -> str:
    """确保兼容端点 URL 格式正确（DeepSeek 等需 /v1 后缀）。"""
    url = url.strip().rstrip("/")
    if not url:
        return DEEPSEEK_DEFAULT_BASE_URL
    if url.endswith("/v1"):
        return url
    # DeepSeek 官方域名未带 /v1 时自动补全
    if "deepseek.com" in url:
        return f"{url}/v1"
    return url


def _get_env(name: str, *fallback_names: str) -> str:
    """读取环境变量，支持旧变量名向后兼容。"""
    value = os.getenv(name, "").strip()
    if value:
        return value
    for fallback in fallback_names:
        value = os.getenv(fallback, "").strip()
        if value:
            return value
    return ""


def get_openai_api_key() -> str:
    """读取 API Key（OPENAI_API_KEY / DEEPSEEK_API_KEY / LLM_API_KEY）。"""
    api_key = _get_env("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "LLM_API_KEY")
    if api_key in _PLACEHOLDER_KEYS:
        raise ValueError(
            "未配置有效的 LLM API Key。请在项目根目录 .env 中设置（DeepSeek 示例）：\n"
            "OPENAI_API_KEY=你的密钥\n"
            "OPENAI_BASE_URL=https://api.deepseek.com/v1\n"
            "OPENAI_MODEL=deepseek-chat\n"
            "（也兼容 DEEPSEEK_API_KEY 或 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL）\n"
            f"（.env 路径：{_ENV_FILE}）"
        )
    return api_key


def get_openai_base_url() -> str:
    """读取 API Base URL。"""
    base_url = _get_env("OPENAI_BASE_URL", "DEEPSEEK_BASE_URL", "LLM_BASE_URL")
    if not base_url:
        return DEEPSEEK_DEFAULT_BASE_URL
    return _normalize_base_url(base_url)


def get_openai_model() -> str:
    return _get_env("OPENAI_MODEL", "DEEPSEEK_MODEL", "LLM_MODEL") or DEFAULT_MODEL


def get_openai_temperature() -> float:
    raw = _get_env("OPENAI_TEMPERATURE", "DEEPSEEK_TEMPERATURE", "LLM_TEMPERATURE")
    if not raw:
        return DEFAULT_TEMPERATURE
    return float(raw)


def is_dotenv_loaded() -> bool:
    """检查 .env 是否已加载且 LLM API Key 可用（非占位符）。每次调用重新读 .env，便于改配置后无需重启。"""
    load_dotenv(dotenv_path=_ENV_FILE, override=True)
    try:
        get_openai_api_key()
        return True
    except ValueError:
        return False


@lru_cache(maxsize=8)
def get_chat_llm(
    model: str | None = None,
    temperature: float | None = None,
    base_url: str | None = None,
) -> ChatOpenAI:
    """创建 ChatOpenAI 实例（显式传入 api_key 与 base_url，避免 invalid_api_key）。"""
    return ChatOpenAI(
        model=model or get_openai_model(),
        api_key=get_openai_api_key(),
        base_url=_normalize_base_url(base_url) if base_url else get_openai_base_url(),
        temperature=temperature if temperature is not None else get_openai_temperature(),
        timeout=120,
        max_retries=2,
    )


__all__ = [
    "DEFAULT_MODEL",
    "DEEPSEEK_DEFAULT_BASE_URL",
    "get_chat_llm",
    "get_openai_api_key",
    "get_openai_base_url",
    "get_openai_model",
    "get_openai_temperature",
    "is_dotenv_loaded",
]
