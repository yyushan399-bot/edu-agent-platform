"""Graph 层统一 RAG 检索：按多路由并行检索，写入 retrieved_contexts。"""

from __future__ import annotations

import logging
from collections.abc import Callable

from rag.data_rag import retrieve_data_context
from rag.practice_rag import retrieve_practice_context
from rag.rag_config import RAG_FALLBACK_HINT, is_rag_enabled
from rag.theory_rag import retrieve_theory_context

logger = logging.getLogger(__name__)
from state import (
    LearningState,
    RetrieveContextNodeUpdate,
    format_merged_retrieved_context,
    get_active_routes,
    normalize_routes,
)

RetrieveFn = Callable[[str], str]

ROUTE_RETRIEVERS: dict[str, RetrieveFn] = {
    "theory": retrieve_theory_context,
    "practice": retrieve_practice_context,
    "data": retrieve_data_context,
}


def retrieve_context_for_route(route: str, query: str) -> str:
    route = normalize_routes(route)[0]
    return ROUTE_RETRIEVERS[route](query)


def _retrieve_route_safe(route: str, query: str) -> str:
    """单路由检索；失败时降级为提示文本，避免整图 500。"""
    if not is_rag_enabled():
        return RAG_FALLBACK_HINT
    try:
        return ROUTE_RETRIEVERS[route](query)
    except Exception as exc:
        logger.warning("RAG retrieve failed (%s): %s", route, exc, exc_info=True)
        return f"{RAG_FALLBACK_HINT}\n（技术原因: {type(exc).__name__}: {exc}）"


def retrieve_contexts_for_routes(
    routes: list[str],
    query: str,
) -> dict[str, str]:
    """为每条路由独立检索，返回 route -> context。"""
    contexts: dict[str, str] = {}
    for route in normalize_routes(routes):
        contexts[route] = _retrieve_route_safe(route, query)
    return contexts


def retrieve_context_node(state: LearningState) -> RetrieveContextNodeUpdate:
    student_input = (state.get("student_input") or "").strip()
    if not student_input:
        raise ValueError("student_input 不能为空")

    routes = get_active_routes(state)
    contexts = retrieve_contexts_for_routes(routes, student_input)
    return {
        "retrieved_contexts": contexts,
        "retrieved_context": format_merged_retrieved_context(contexts),
    }


__all__ = [
    "ROUTE_RETRIEVERS",
    "retrieve_context_for_route",
    "retrieve_context_node",
    "retrieve_contexts_for_routes",
]
