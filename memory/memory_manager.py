"""长期记忆管理器：评估写入 + 历史检索（不依赖 LangGraph 图内节点）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from memory.evaluation_store import (
    DEFAULT_MEMORY_DIR,
    append_evaluation,
    build_evaluation_record,
    delete_student_memory,
    get_memory_path,
    list_evaluations,
    load_student_memory,
    sanitize_student_id,
    save_student_memory,
)
from memory.memory_retriever import (
    retrieve_memory_context,
    retrieve_recent_evaluations,
    retrieve_student_profile,
)


class MemoryManager:
    """
    学生长期记忆门面。

    - 每个 student_id 对应一个 JSON 文件（data/memory/students/{id}.json）
    - 图执行前后由入口层调用，不修改 graph 结构
    """

    def __init__(
        self,
        student_id: str,
        *,
        memory_dir: Path | str | None = None,
        max_records: int = 100,
        default_retrieve_k: int = 3,
    ) -> None:
        self.student_id = sanitize_student_id(student_id)
        self.memory_dir = Path(memory_dir) if memory_dir else DEFAULT_MEMORY_DIR
        self.max_records = max_records
        self.default_retrieve_k = default_retrieve_k

    @property
    def memory_path(self) -> Path:
        return get_memory_path(self.student_id, memory_dir=self.memory_dir)

    def load(self) -> dict[str, Any]:
        return load_student_memory(self.student_id, memory_dir=self.memory_dir)

    def save(self, memory: dict[str, Any]) -> Path:
        return save_student_memory(
            self.student_id, memory, memory_dir=self.memory_dir
        )

    def record_evaluation(
        self,
        state: dict[str, Any],
        *,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """从 LangGraph 返回的 state dict 追加一条评估记录。"""
        record = build_evaluation_record(
            student_input=str(state.get("student_input") or ""),
            routes=state.get("routes"),
            route=state.get("route"),
            route_reason=state.get("route_reason"),
            theory_result=state.get("theory_result"),
            practice_result=state.get("practice_result"),
            data_result=state.get("data_result"),
            literature_result=state.get("literature_result"),
            total_score=state.get("total_score"),
            score_detail=state.get("score_detail"),
            final_feedback=state.get("final_feedback"),
            history_memory=state.get("history_memory"),
            uploaded_files=state.get("uploaded_files"),
            extra=extra,
        )
        return append_evaluation(
            self.student_id,
            record,
            memory_dir=self.memory_dir,
            max_records=self.max_records,
        )

    def get_recent(self, k: int | None = None) -> list[dict[str, Any]]:
        return retrieve_recent_evaluations(
            self.student_id,
            k=k or self.default_retrieve_k,
            memory_dir=self.memory_dir,
        )

    def get_context(
        self,
        *,
        k: int | None = None,
        query: str | None = None,
    ) -> str:
        """检索格式化的长期记忆文本。"""
        return retrieve_memory_context(
            self.student_id,
            k=k or self.default_retrieve_k,
            memory_dir=self.memory_dir,
            query=query,
        )

    def enrich_student_input(
        self,
        student_input: str,
        *,
        k: int | None = None,
        query: str | None = None,
    ) -> str:
        """
        将长期记忆前置到学生输入（供入口层注入，不修改 graph）。

        若无历史记录则原样返回 student_input。
        """
        context = self.get_context(k=k, query=query or student_input)
        if context.startswith("（该学生暂无"):
            return student_input
        return (
            f"【学生历史评估记忆 — {self.student_id}】\n{context}\n\n"
            f"【本次提交】\n{student_input}"
        )

    def profile(self) -> dict[str, Any]:
        return retrieve_student_profile(
            self.student_id, memory_dir=self.memory_dir
        )

    def list_all(self, limit: int | None = None) -> list[dict[str, Any]]:
        return list_evaluations(
            self.student_id,
            memory_dir=self.memory_dir,
            limit=limit,
        )

    def clear(self) -> bool:
        return delete_student_memory(self.student_id, memory_dir=self.memory_dir)


def record_evaluation_for_student(
    student_id: str,
    state: dict[str, Any],
    *,
    memory_dir: Path | None = None,
    max_records: int = 100,
) -> dict[str, Any]:
    """便捷函数：保存单次评估。"""
    return MemoryManager(
        student_id, memory_dir=memory_dir, max_records=max_records
    ).record_evaluation(state)


def get_memory_context_for_student(
    student_id: str,
    *,
    k: int = 3,
    query: str | None = None,
    memory_dir: Path | None = None,
) -> str:
    """便捷函数：检索长期记忆文本。"""
    return MemoryManager(
        student_id, memory_dir=memory_dir, default_retrieve_k=k
    ).get_context(k=k, query=query)


__all__ = [
    "MemoryManager",
    "get_memory_context_for_student",
    "record_evaluation_for_student",
]
