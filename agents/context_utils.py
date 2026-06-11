"""各评估 agent 读取 RAG + Deep Research 上下文的工具。"""

from __future__ import annotations

from state import LearningState, get_active_routes

_EMPTY_CONTEXT = "（无参考资料，请仅依据学生作答内容进行评估。）"
EMPTY_MEMORY_CONTEXT = "（无历史评估记录，请仅依据本次作答评估。）"

_RESEARCH_SKIP_PREFIXES = (
    "（未启用深度联网研究",
    "（未检索到可用资料",
)


def get_route_context(state: LearningState, route: str) -> str:
    """
    获取指定路由的 RAG 参考文本。

    优先 retrieved_contexts[route]；单路由时回退 retrieved_context。
    """
    route = route.strip().lower()
    contexts = state.get("retrieved_contexts") or {}
    if route in contexts:
        text = (contexts[route] or "").strip()
        if text:
            return text

    active = get_active_routes(state)
    legacy = (state.get("retrieved_context") or "").strip()
    if legacy and len(active) == 1 and active[0] == route:
        return legacy
    return _EMPTY_CONTEXT


def get_research_context(state: LearningState) -> str:
    """获取 Deep Research 摘要（内部参考，不含网页原文）。"""
    text = (state.get("research_context") or "").strip()
    if not text or any(text.startswith(p) for p in _RESEARCH_SKIP_PREFIXES):
        return ""
    return text


def get_memory_context(state: LearningState) -> str:
    """获取长期记忆文本（retrieve_memory_node 写入的 memory_context）。"""
    from memory.memory_retriever import EMPTY_MEMORY_HINT

    text = (state.get("memory_context") or "").strip()
    if not text or text == EMPTY_MEMORY_HINT:
        return EMPTY_MEMORY_CONTEXT
    return text


def build_reference_context(state: LearningState, route: str) -> str:
    """
    合并知识库检索与联网研究摘要，供 theory/practice/data 评估使用。

    不向学生展示网页链接或原文；仅将摘要作为教师侧参考资料。
    """
    parts: list[str] = []

    research = get_research_context(state)
    if research:
        parts.append(
            "【领域背景资料（供评估对照，须融入形成性评价 feedback，勿向学生暴露链接或来源）】\n"
            f"{research}"
        )

    rag = get_route_context(state, route)
    if rag and rag != _EMPTY_CONTEXT:
        parts.append(f"【知识库检索】\n{rag}")
    elif not parts:
        return _EMPTY_CONTEXT

    return "\n\n".join(parts)


__all__ = [
    "EMPTY_MEMORY_CONTEXT",
    "build_reference_context",
    "get_memory_context",
    "get_research_context",
    "get_route_context",
]
