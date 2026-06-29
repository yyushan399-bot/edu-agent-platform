"""章节反馈（学生反馈项目）统一配置。"""

from __future__ import annotations

import os

from agents.group_project.pbl_config import DEFAULT_MODEL, DEFAULT_SCORING_TIMES
from utils.section_constants import SECTION_NAMES

DEFAULT_CV_THRESHOLD = float(os.getenv("SECTION_CV_THRESHOLD", "0.20"))
DEFAULT_MAX_REVIEW_ROUNDS = int(os.getenv("SECTION_MAX_REVIEW_ROUNDS", "3"))

from data.section_rag.graphrag_config import (
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    SECTION_GRAPHRAG_BACKEND,
    SECTION_GRAPHRAG_JSON_PATH,
    neo4j_configured,
)

REFERENCE_LEAK_MARKERS = [
    "GraphRAG",
    "graphrag",
    "参考报告",
    "参考片段",
    "优质报告",
    "普通报告",
    "样例报告",
    "对照样例",
    "检索片段",
    "exemplar",
    "ScoreDescriptor",
    "ReportChunk",
    "Neo4j",
]


__all__ = [
    "DEFAULT_CV_THRESHOLD",
    "DEFAULT_MAX_REVIEW_ROUNDS",
    "DEFAULT_MODEL",
    "DEFAULT_SCORING_TIMES",
    "NEO4J_PASSWORD",
    "NEO4J_URI",
    "NEO4J_USER",
    "REFERENCE_LEAK_MARKERS",
    "SECTION_GRAPHRAG_BACKEND",
    "SECTION_GRAPHRAG_JSON_PATH",
    "SECTION_NAMES",
    "neo4j_configured",
]
