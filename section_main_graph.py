"""章节反馈 LangGraph 工作流（独立于四路由 / PBL 主图）。"""

from __future__ import annotations

import llm_config  # noqa: F401

from langgraph.graph import END, START, StateGraph

from agents.retrieve_memory_node import retrieve_memory_node
from agents.save_memory_node import save_memory_node
from agents.section_report.section_evaluation_node import section_evaluation_node
from agents.section_report.section_split_node import section_split_node
from agents.section_report.section_summary_node import section_summary_node
from state import LearningState, create_section_initial_state


def build_section_graph():
    """
    章节反馈链：

    START -> retrieve_memory -> section_split -> section_evaluation
         -> section_summary -> save_memory -> END
    """
    builder = StateGraph(LearningState)

    builder.add_node("retrieve_memory_node", retrieve_memory_node)
    builder.add_node("section_split_node", section_split_node)
    builder.add_node("section_evaluation_node", section_evaluation_node)
    builder.add_node("section_summary_node", section_summary_node)
    builder.add_node("save_memory_node", save_memory_node)

    builder.add_edge(START, "retrieve_memory_node")
    builder.add_edge("retrieve_memory_node", "section_split_node")
    builder.add_edge("section_split_node", "section_evaluation_node")
    builder.add_edge("section_evaluation_node", "section_summary_node")
    builder.add_edge("section_summary_node", "save_memory_node")
    builder.add_edge("save_memory_node", END)

    return builder.compile()


section_main_graph = build_section_graph()
section_app = section_main_graph


def run_section_workflow(
    report_text: str,
    *,
    section_name: str | None = None,
    section_texts: dict[str, str] | None = None,
    student_id: str | None = None,
    session_id: str | None = None,
    enable_section_review: bool = True,
    section_scoring_times: int | None = None,
    section_review_rounds: int | None = None,
    section_cv_threshold: float | None = None,
    memory_retrieve_k: int = 3,
) -> LearningState:
    """运行章节反馈工作流。"""
    initial = create_section_initial_state(
        report_text,
        section_name=section_name,
        section_texts=section_texts,
        student_id=student_id,
        session_id=session_id,
        enable_section_review=enable_section_review,
        section_scoring_times=section_scoring_times,
        section_review_rounds=section_review_rounds,
        section_cv_threshold=section_cv_threshold,
        memory_retrieve_k=memory_retrieve_k,
    )
    return section_app.invoke(initial)


__all__ = [
    "build_section_graph",
    "run_section_workflow",
    "section_app",
    "section_main_graph",
]
