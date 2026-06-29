"""PBL 小组项目评价 LangGraph 工作流（独立于四路由主图）。"""

from __future__ import annotations

import llm_config  # noqa: F401

from langgraph.graph import END, START, StateGraph

from agents.group_project.group_evaluation_node import group_evaluation_node
from agents.retrieve_memory_node import retrieve_memory_node
from agents.save_memory_node import save_memory_node
from state import LearningState, create_pbl_initial_state


def build_pbl_graph():
    """
    PBL 评价链：

    START -> retrieve_memory -> group_evaluation -> save_memory -> END
    """
    builder = StateGraph(LearningState)

    builder.add_node("retrieve_memory_node", retrieve_memory_node)
    builder.add_node("group_evaluation_node", group_evaluation_node)
    builder.add_node("save_memory_node", save_memory_node)

    builder.add_edge(START, "retrieve_memory_node")
    builder.add_edge("retrieve_memory_node", "group_evaluation_node")
    builder.add_edge("group_evaluation_node", "save_memory_node")
    builder.add_edge("save_memory_node", END)

    return builder.compile()


pbl_main_graph = build_pbl_graph()
pbl_app = pbl_main_graph


def run_pbl_workflow(
    report_text: str,
    *,
    student_id: str | None = None,
    session_id: str | None = None,
    enable_pbl_review: bool = False,
    pbl_scoring_times: int = 10,
    pbl_rag_top_k: int = 8,
    pbl_review_rounds: int = 5,
    memory_retrieve_k: int = 3,
) -> LearningState:
    """运行 PBL 评价工作流。"""
    initial = create_pbl_initial_state(
        report_text,
        student_id=student_id,
        session_id=session_id,
        enable_pbl_review=enable_pbl_review,
        pbl_scoring_times=pbl_scoring_times,
        pbl_rag_top_k=pbl_rag_top_k,
        pbl_review_rounds=pbl_review_rounds,
        memory_retrieve_k=memory_retrieve_k,
    )
    return pbl_app.invoke(initial)


__all__ = [
    "build_pbl_graph",
    "pbl_app",
    "pbl_main_graph",
    "run_pbl_workflow",
]
