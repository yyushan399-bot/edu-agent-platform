"""
量规加载工具 —— 供各 Agent 和 scoring_node 使用

用法：
    from rubrics.load_rubric import RubricLoader

    loader = RubricLoader()
    full = loader.get_scoring_rubric()         # 完整量规
    theory = loader.get_dimension("theory")    # 单个维度
    collab = loader.get_collab_rubric()        # 协作量规
    prompt = loader.get_agent_prompt("theory") # 给 Theory Agent 的 prompt 块
"""

import json
import os
from typing import Optional

_RUBRIC_DIR = os.path.dirname(os.path.abspath(__file__))


class RubricLoader:
    """加载并访问量规数据."""

    def __init__(self):
        self._scoring: Optional[dict] = None
        self._collab: Optional[dict] = None
        self._dim_index: Optional[dict] = None

    # ── 加载 ────────────────────────────────────────────

    def get_scoring_rubric(self) -> dict:
        if self._scoring is None:
            self._scoring = self._load("scoring_rubric_v4.json")
        return self._scoring

    def get_collab_rubric(self) -> dict:
        if self._collab is None:
            self._collab = self._load("collab_rubric.json")
        return self._collab

    def _load(self, filename: str) -> dict:
        path = os.path.join(_RUBRIC_DIR, filename)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ── 维度访问 ────────────────────────────────────────

    def _build_dim_index(self):
        if self._dim_index is not None:
            return
        rubric = self.get_scoring_rubric()
        self._dim_index = {}
        for dim in rubric["dimensions"]:
            self._dim_index[dim["id"]] = dim
            self._dim_index[dim["agent"].lower()] = dim

    def list_dimensions(self) -> list[dict]:
        """列出所有维度."""
        return self.get_scoring_rubric()["dimensions"]

    def get_dimension(self, key: str) -> Optional[dict]:
        """按维度 id 或 agent 名查找维度，如 key="theory" 或 "Theory Agent"."""
        self._build_dim_index()
        return self._dim_index.get(key.lower())

    def get_sub_indicator(self, dim_key: str, sub_id: str) -> Optional[dict]:
        """获取某个维度下的二级指标."""
        dim = self.get_dimension(dim_key)
        if dim is None:
            return None
        for sub in dim["sub_indicators"]:
            if sub["id"] == sub_id:
                return sub
        return None

    # ── Agent Prompt 生成 ───────────────────────────────

    def get_agent_prompt(self, dim_key: str) -> str:
        """生成适合注入 Agent system prompt 的评分标准文本.

        Args:
            dim_key: 维度 id，如 "theory", "practice", "data", "literature"

        Returns:
            Markdown 格式的评分标准文本，可以直接拼入 system prompt
        """
        dim = self.get_dimension(dim_key)
        if dim is None:
            return f"# 错误：未找到维度 '{dim_key}'"

        lines = [f"## {dim['name']}（{dim['agent']}）", ""]
        lines.append(f"{dim['description']}")
        lines.append("")

        for sub in dim["sub_indicators"]:
            lines.append(f"### {sub['name']}")
            for score in ["5", "4", "3", "2", "1"]:
                desc = sub["levels"].get(score, "")
                label = dim["label"] if (dim_label := "") else ""
                lines.append(f"- **{score}分**: {desc}")
            lines.append("")

        lines.append(f"**计算公式**: {dim['formula']}")
        lines.append("")
        lines.append("**评分要求**:")
        lines.append("- 每个二级指标使用 1-5 分制整数评分")
        lines.append("- 评分须附带具体、可操作的文字反馈（优点 + 不足 + 改进方向）")
        lines.append("")

        return "\n".join(lines)

    def get_scoring_node_prompt(self) -> str:
        """给 scoring_node 的聚合规则."""
        return """# scoring_node 评分聚合规则

## 核心逻辑
total_score = 算术平均所有激活维度的维度综合分

## 关键行为（由 get_active_routes() 保证）
- 学生只提交文献 → routes = ["literature"] → total_score = literature_agent 独自得分
- 学生提交理论和数据 → routes = ["theory", "data"] → total_score = 两者算术平均
- 学生四维度都提交 → total_score = 四者算术平均

## 维度综合分公式
- 理论维 = round((概念准确性 + 逻辑完整性 + 理论迁移) / 3, 2)
- 实践维 = round((方案设计 + 操作规范性 + 问题解决) / 3, 2)
- 数据维 = round((数据采集 + 数据分析 + 可视化) / 3, 2)
- 文献维 = round((文献理解 + 观点一致性 + 批判思考 + 创新延伸) / 4, 2)

## 注意事项
- 不需要引入固定权重（学生分角色提交，组内分工）
- 每个二级指标须附带 feedback 字段，不能只给分数
"""
