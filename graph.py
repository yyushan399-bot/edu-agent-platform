"""兼容入口：从 main_graph 重新导出图与运行函数。"""

from __future__ import annotations

import json

import llm_config  # noqa: F401

from main_graph import app, build_graph, main_graph, run_workflow
from state import LearningState, create_initial_state

__all__ = [
    "LearningState",
    "app",
    "build_graph",
    "create_initial_state",
    "main_graph",
    "run_workflow",
]


if __name__ == "__main__":
    sample_input = "牛顿第二定律 F=ma 中，力与加速度成正比。"
    result = run_workflow(sample_input)
    print(json.dumps(dict(result), ensure_ascii=False, indent=2))
