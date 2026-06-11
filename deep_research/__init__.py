"""Deep Research：博查搜索 + 网页抓取 + LLM 总结。"""

from deep_research.config import get_bocha_api_key, is_deep_research_enabled
from deep_research.pipeline import EMPTY_RESEARCH, run_deep_research

__all__ = [
    "EMPTY_RESEARCH",
    "get_bocha_api_key",
    "is_deep_research_enabled",
    "run_deep_research",
]
