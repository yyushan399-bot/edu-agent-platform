"""PBL 小组项目评价统一配置（环境变量可覆盖）。"""

from __future__ import annotations

import os

DEEPSEEK_BASE_URL = os.getenv(
    "OPENAI_BASE_URL",
    os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
)
DEFAULT_MODEL = os.getenv(
    "OPENAI_MODEL",
    os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
)

# 生产默认 10 次；测试/CI 可设 TEST_SCORING_TIMES=1 或 PBL_SCORING_TIMES=1
DEFAULT_SCORING_TIMES = int(os.getenv("PBL_SCORING_TIMES", "10"))
DEFAULT_RAG_TOP_K = int(os.getenv("PBL_RAG_TOP_K", "8"))
DEFAULT_REVIEW_ROUNDS = int(os.getenv("PBL_REVIEW_ROUNDS", "5"))

PBL_CACHE_ENABLED = os.getenv("PBL_CACHE_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
PBL_CACHE_DIR = os.getenv("PBL_CACHE_DIR", "data/cache/pbl_evaluations")
PBL_CACHE_TTL_HOURS = int(os.getenv("PBL_CACHE_TTL_HOURS", "168"))

__all__ = [
    "DEEPSEEK_BASE_URL",
    "DEFAULT_MODEL",
    "DEFAULT_RAG_TOP_K",
    "DEFAULT_REVIEW_ROUNDS",
    "DEFAULT_SCORING_TIMES",
    "PBL_CACHE_DIR",
    "PBL_CACHE_ENABLED",
    "PBL_CACHE_TTL_HOURS",
]
