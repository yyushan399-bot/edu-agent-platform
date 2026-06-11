"""Graph 节点：Deep Research → 写入 research_context。"""

from __future__ import annotations

from deep_research import EMPTY_RESEARCH, is_deep_research_enabled, run_deep_research
from state import DeepResearchNodeUpdate, LearningState


def deep_research_node(state: LearningState) -> DeepResearchNodeUpdate:
    """
    根据 student_input 联网研究，结果写入 research_context。

    不向学生暴露网页原文或链接，仅保留 LLM 摘要。
    """
    student_input = (state.get("student_input") or "").strip()
    if not student_input:
        raise ValueError("student_input 不能为空")

    if state.get("enable_deep_research") is False:
        return {"research_context": EMPTY_RESEARCH}

    if not is_deep_research_enabled():
        return {"research_context": EMPTY_RESEARCH}

    context = run_deep_research(student_input)
    return {"research_context": context}


__all__ = ["deep_research_node"]
