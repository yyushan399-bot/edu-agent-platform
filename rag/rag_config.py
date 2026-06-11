"""RAG 开关与降级提示。"""

from __future__ import annotations

import os

RAG_FALLBACK_HINT = (
    "（知识库检索暂不可用，请仅依据学生作答内容进行评估。）"
)


def is_rag_enabled() -> bool:
    """是否启用向量检索（RAG_ENABLED=false 时跳过 BGE/Chroma）。"""
    raw = os.getenv("RAG_ENABLED", "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


__all__ = ["RAG_FALLBACK_HINT", "is_rag_enabled"]
