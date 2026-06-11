"""LangGraph 主工作流：记忆 → 监督 → Deep Research → RAG → 并行评估 → 综合 → 存记忆。"""

from __future__ import annotations

import llm_config  # noqa: F401

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agents.literature_agent import literature_node
from agents.data_agent import data_node
from agents.deep_research_node import deep_research_node
from agents.practice_agent import practice_node
from agents.retrieve_context_node import retrieve_context_node
from agents.retrieve_memory_node import retrieve_memory_node
from agents.scoring_node import scoring_node
from agents.save_memory_node import save_memory_node
from agents.supervisor_agent import supervisor_node
from agents.synthesis_agent import synthesis_node
from state import LearningState, ROUTE_TO_NODE, create_initial_state, get_active_routes
from theory_agent import theory_node


def fan_out_evaluators(state: LearningState) -> list[Send]:
    """按 routes 动态扇出到多个评估 agent（并行执行）。"""
    routes = get_active_routes(state)
    sends: list[Send] = []
    for route in routes:
        node_name = ROUTE_TO_NODE.get(route)
        if node_name:
            sends.append(Send(node_name, state))
    if not sends:
        sends.append(Send("theory_agent", state))
    return sends


def build_graph():
    """
    构建工作流：

    START -> retrieve_memory -> supervisor -> deep_research -> retrieve_context
         -> [Send] theory / practice / data / literature -> scoring -> synthesis -> save_memory -> END
    """
    builder = StateGraph(LearningState)

    builder.add_node("retrieve_memory_node", retrieve_memory_node)
    builder.add_node("supervisor_agent", supervisor_node)
    builder.add_node("deep_research_node", deep_research_node)
    builder.add_node("retrieve_context_node", retrieve_context_node)
    builder.add_node("theory_agent", theory_node)
    builder.add_node("practice_agent", practice_node)
    builder.add_node("data_agent", data_node)
    builder.add_node("literature_agent", literature_node)
    builder.add_node("scoring_node", scoring_node)
    builder.add_node("synthesis_agent", synthesis_node)
    builder.add_node("save_memory_node", save_memory_node)

    builder.add_edge(START, "retrieve_memory_node")
    builder.add_edge("retrieve_memory_node", "supervisor_agent")
    builder.add_edge("supervisor_agent", "deep_research_node")
    builder.add_edge("deep_research_node", "retrieve_context_node")
    builder.add_conditional_edges(
        "retrieve_context_node",
        fan_out_evaluators,
        ["theory_agent", "practice_agent", "data_agent", "literature_agent"],
    )

    builder.add_edge("theory_agent", "scoring_node")
    builder.add_edge("practice_agent", "scoring_node")
    builder.add_edge("data_agent", "scoring_node")
    builder.add_edge("literature_agent", "scoring_node")
    builder.add_edge("scoring_node", "synthesis_agent")
    builder.add_edge("synthesis_agent", "save_memory_node")
    builder.add_edge("save_memory_node", END)

    return builder.compile()


main_graph = build_graph()
app = main_graph


def run_workflow(
    student_input: str,
    *,
    routes: list[str] | None = None,
    student_id: str | None = None,
    memory_retrieve_k: int = 3,
    enable_deep_research: bool | None = None,
) -> LearningState:
    """运行工作流；可选预设 routes / student_id / Deep Research。"""
    initial = create_initial_state(
        student_input,
        routes=routes,
        student_id=student_id,
        memory_retrieve_k=memory_retrieve_k,
        enable_deep_research=enable_deep_research,
    )
    return app.invoke(initial)
