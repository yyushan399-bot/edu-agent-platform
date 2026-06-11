"""Graph 节点：按 student_id 检索长期记忆，写入 memory_context 与 evaluation_history。"""

from __future__ import annotations

from memory.evaluation_store import list_evaluations
from memory.memory_manager import MemoryManager
from memory.memory_retriever import EMPTY_MEMORY_HINT, retrieve_memory_context
from state import EvaluationRecord, LearningState, RetrieveMemoryNodeUpdate

DEFAULT_MEMORY_K = 3


def retrieve_memory_node(state: LearningState) -> RetrieveMemoryNodeUpdate:
    """
    根据 state["student_id"] 读取历史评价。

    - memory_context：格式化摘要文本
    - evaluation_history：结构化记录列表
    """
    student_id = (state.get("student_id") or "").strip()
    if not student_id:
        return {
            "memory_context": EMPTY_MEMORY_HINT,
            "evaluation_history": [],
        }

    query = (state.get("student_input") or "").strip() or None
    k = int(state.get("memory_retrieve_k") or DEFAULT_MEMORY_K)

    context = retrieve_memory_context(
        student_id,
        k=k,
        query=query,
    )
    try:
        records: list[EvaluationRecord] = list(
            list_evaluations(student_id, limit=k)
        )
    except FileNotFoundError:
        records = []

    return {
        "memory_context": context,
        "evaluation_history": records,
    }


def retrieve_memory_for_student(
    student_id: str,
    *,
    k: int = DEFAULT_MEMORY_K,
    query: str | None = None,
) -> str:
    """便捷函数：不经过图直接检索记忆文本。"""
    return MemoryManager(student_id, default_retrieve_k=k).get_context(
        k=k, query=query
    )


__all__ = [
    "DEFAULT_MEMORY_K",
    "retrieve_memory_for_student",
    "retrieve_memory_node",
]
