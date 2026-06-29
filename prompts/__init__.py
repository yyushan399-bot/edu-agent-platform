"""Agent Prompt 模板包 —— 为每个评分智能体提供注入量规的 system prompt.

用法：
    from prompts import build_agent_prompt

    prompt = build_agent_prompt("theory", student_submission)
    # 将 prompt 作为 system message 发给 LLM
"""
from .agent_templates import build_agent_prompt, build_scoring_node_prompt, build_meta_eval_prompt

__all__ = ["build_agent_prompt", "build_scoring_node_prompt", "build_meta_eval_prompt"]
