"""Deep Research 配置（博查 + LLM）。"""

from __future__ import annotations

import os

BOCHA_WEB_SEARCH_URL = "https://api.bochaai.com/v1/web-search"

DEFAULT_MAX_PAGES = int(os.getenv("DEEP_RESEARCH_MAX_PAGES", "5"))
DEFAULT_SEARCH_COUNT = int(os.getenv("DEEP_RESEARCH_SEARCH_COUNT", "8"))
DEFAULT_FETCH_TIMEOUT = int(os.getenv("DEEP_RESEARCH_FETCH_TIMEOUT", "15"))
DEFAULT_MAX_PAGE_CHARS = int(os.getenv("DEEP_RESEARCH_MAX_PAGE_CHARS", "12000"))


def _env(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def get_bocha_api_key() -> str:
    return _env("BOCHA_API_KEY", "BOCHAAI_API_KEY", "BOCHAAI_SEARCH_API_KEY")


def is_deep_research_enabled() -> bool:
    flag = _env("DEEP_RESEARCH_ENABLED").lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    if flag in {"1", "true", "yes", "on"}:
        return bool(get_bocha_api_key())
    return bool(get_bocha_api_key())


__all__ = [
    "BOCHA_WEB_SEARCH_URL",
    "DEFAULT_FETCH_TIMEOUT",
    "DEFAULT_MAX_PAGE_CHARS",
    "DEFAULT_MAX_PAGES",
    "DEFAULT_SEARCH_COUNT",
    "get_bocha_api_key",
    "is_deep_research_enabled",
]
