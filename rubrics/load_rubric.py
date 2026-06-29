"""RubricLoader — 供 prompts/agent_templates 使用的量规加载门面。"""

from __future__ import annotations

from rubrics.rubric_prompt_utils import (
    format_dimension_rubric_block,
    get_sub_indicator_ids,
)


class RubricLoader:
    """从 scoring_rubric_v4.json 读取量规文本。"""

    def get_agent_prompt(self, dimension_id: str) -> str:
        return format_dimension_rubric_block(dimension_id)

    def get_scoring_node_prompt(self) -> str:
        return (
            "各路由 Agent 输出 0-100 百分制 score，并附带 1-5 二级指标分。"
            "scoring_node 汇总已执行路由的 score 算术平均为 total_score，"
            "并将各路由 sub_scores 写入 score_detail.sub_scores。"
        )

    def get_sub_indicator_ids(self, dimension_id: str) -> list[str]:
        return get_sub_indicator_ids(dimension_id)


__all__ = ["RubricLoader"]
