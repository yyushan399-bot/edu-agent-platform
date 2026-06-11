"""Graph 节点：将本次评估结果写入长期记忆 JSON，并追加 evaluation_history。"""

from __future__ import annotations

from memory.memory_manager import MemoryManager
from state import EvaluationRecord, LearningState, SaveMemoryNodeUpdate


def save_memory_node(state: LearningState) -> SaveMemoryNodeUpdate:
    """
    根据 state["student_id"] 持久化本次评价。

    无 student_id 时跳过写入。
    """
    student_id = (state.get("student_id") or "").strip()
    if not student_id:
        return {}

    mgr = MemoryManager(student_id)
    record: EvaluationRecord = mgr.record_evaluation(dict(state))
    return {
        "last_saved_evaluation_id": record.get("evaluation_id", ""),
        "evaluation_history": [record],
    }


__all__ = ["save_memory_node"]
