"""
Agent Prompt 模板 —— 将量规注入各评分智能体的 system prompt.

用法：
    from prompts import build_agent_prompt

    msgs = build_agent_prompt("theory", student_submission)
    # msgs[0] = system message, msgs[1] = user message
"""

import json
from rubrics.load_rubric import RubricLoader

_loader = RubricLoader()

# ── Agent 角色定义 ─────────────────────────────────────

AGENT_ROLES = {
    "theory": {
        "name": "Theory Agent",
        "title": "理论评估智能体",
        "role": (
            "你是一位教育评估智能体，专门负责从理论维度评价学生的项目报告。"
            "你需要仔细阅读学生的提交内容，依据量规对每个二级指标进行 1-5 分评分，"
            "并给出具体、可操作的形成性反馈。"
        ),
        "output_example": {
            "scores": {
                "concept_accuracy": 4,
                "logic_integrity": 4,
                "theory_transfer": 3
            },
            "feedbacks": {
                "concept_accuracy": "概念定义基本准确，术语使用规范。但对概念适用边界的讨论可以更加深入……",
                "logic_integrity": "论证结构合理，但部分推理步骤存在跳跃……",
                "theory_transfer": "能与项目情境建立基本关联，但缺乏对理论的深层分析……"
            },
            "summary": "该生在理论维度表现良好，概念理解和论证框架扎实，但在理论迁移深度上还有提升空间。",
            "dimension_score": 3.67
        }
    },
    "practice": {
        "name": "Practice Agent",
        "title": "实践评估智能体",
        "role": (
            "你是一位教育评估智能体，专门负责从实践维度评价学生的项目报告。"
            "你需要评估方案设计、操作规范性和问题诊断能力。"
        ),
        "output_example": {
            "scores": {
                "design_completeness": 4,
                "operational_standard": 4,
                "problem_solving": 3
            },
            "feedbacks": {
                "design_completeness": "...",
                "operational_standard": "...",
                "problem_solving": "..."
            },
            "summary": "整体评语",
            "dimension_score": 3.67
        }
    },
    "data": {
        "name": "Data Agent",
        "title": "数据评估智能体",
        "role": (
            "你是一位教育评估智能体，专门负责从数据维度评价学生的项目报告。"
            "你需要评估数据采集处理、数据分析解读和可视化建模的规范性。"
        ),
        "output_example": {
            "scores": {
                "data_collection": 4,
                "data_analysis": 4,
                "visualization": 3
            },
            "feedbacks": {
                "data_collection": "...",
                "data_analysis": "...",
                "visualization": "..."
            },
            "summary": "整体评语",
            "dimension_score": 3.67
        }
    },
    "literature": {
        "name": "Literature Agent",
        "title": "文献评估智能体",
        "role": (
            "你是一位教育评估智能体，专门负责从文献维度评价学生的阅读心得或文献综述。"
            "你需要评估文献理解、观点一致性、批判性思考和创新延伸四个方面。"
        ),
        "output_example": {
            "scores": {
                "lit_understanding": 4,
                "viewpoint_consistency": 4,
                "critical_thinking": 3,
                "innovation_extension": 3
            },
            "feedbacks": {
                "lit_understanding": "...",
                "viewpoint_consistency": "...",
                "critical_thinking": "...",
                "innovation_extension": "..."
            },
            "summary": "整体评语",
            "dimension_score": 3.5
        }
    }
}

# ── Agent 默认 score keys（用于 dimension_score 计算）──

SCORE_KEYS = {
    "theory": ["concept_accuracy", "logic_integrity", "theory_transfer"],
    "practice": ["design_completeness", "operational_standard", "problem_solving"],
    "data": ["data_collection", "data_analysis", "visualization"],
    "literature": ["lit_understanding", "viewpoint_consistency", "critical_thinking", "innovation_extension"],
}


def build_agent_prompt(dim_key: str, student_submission: str) -> list[dict]:
    """构建给 LLM 的 messages 列表（system + user）.

    Args:
        dim_key: 维度 id ("theory" / "practice" / "data" / "literature")
        student_submission: 学生提交的原始内容

    Returns:
        [{"role": "system", "content": ...}, {"role": "user", "content": ...}]
    """
    role_info = AGENT_ROLES.get(dim_key)
    if role_info is None:
        raise ValueError(f"未知维度: {dim_key}，可选: {list(AGENT_ROLES.keys())}")

    rubric_block = _loader.get_agent_prompt(dim_key)

    system_parts = [
        f"# {role_info['title']}（{role_info['name']}）",
        "",
        role_info["role"],
        "",
        "=" * 60,
        "# 评分标准（量规）",
        "",
        rubric_block,
        "=" * 60,
        "# 输出格式要求",
        "",
        "请严格按照以下 JSON 格式返回评分结果：",
        "",
        "```json",
        json.dumps(role_info["output_example"], ensure_ascii=False, indent=2),
        "```",
        "",
        "⚠ 要求：",
        "1. scores 使用 1-5 分制整数",
        "2. feedbacks 必须提供具体文字反馈（优点 + 不足 + 改进方向），不能只给分数",
        f"3. dimension_score = 各 scores 的算术平均（保留两位小数）",
        "4. 返回的 JSON 必须合法，不要包含多余注释",
        "5. 请务必包含所有字段（scores、feedbacks、summary、dimension_score）",
    ]

    system_content = "\n".join(system_parts)
    user_content = f"请评估以下学生提交内容：\n\n---\n{student_submission}\n---"

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def validate_agent_output(parsed: dict, dim_key: str) -> list[str]:
    """校验 agent 返回的 JSON 是否符合格式要求.

    Args:
        parsed: agent 返回的解析后 dict
        dim_key: 维度 id

    Returns:
        错误信息列表。空列表表示校验通过。
    """
    errors = []
    keys = SCORE_KEYS.get(dim_key, [])

    if "scores" not in parsed:
        errors.append("缺少 scores 字段")
    else:
        scores = parsed["scores"]
        for k in keys:
            val = scores.get(k)
            if val is None:
                errors.append(f"scores 缺少 {k}")
            elif not isinstance(val, int) or val < 1 or val > 5:
                errors.append(f"{k} 的值 {val} 不是 1-5 的整数")

    if "feedbacks" not in parsed:
        errors.append("缺少 feedbacks 字段")
    else:
        for k in keys:
            if k not in parsed.get("feedbacks", {}):
                errors.append(f"feedbacks 缺少 {k}")

    if "summary" not in parsed:
        errors.append("缺少 summary 字段")

    if "dimension_score" not in parsed:
        errors.append("缺少 dimension_score 字段")
    else:
        ds = parsed["dimension_score"]
        if not isinstance(ds, (int, float)) or ds < 1 or ds > 5:
            errors.append(f"dimension_score 的值 {ds} 不在 1-5 范围内")

    return errors


def compute_dimension_score(scores: dict, dim_key: str) -> float:
    """手动计算维度综合分（用于 fallback/scoring_node 聚合）. """
    keys = SCORE_KEYS.get(dim_key, [])
    vals = [scores[k] for k in keys if k in scores]
    if not vals:
        return 0.0
    return round(sum(vals) / len(vals), 2)


def build_scoring_node_prompt() -> str:
    """构建 scoring_node 的聚合规则说明."""
    return _loader.get_scoring_node_prompt()


def build_meta_eval_prompt(
    scores_detail: dict,
    collaboration_score: float,
    self_cal_data: dict,
    peer_cal_data: dict,
    previous_rounds: list | None = None,
) -> str:
    """构建 meta_evaluation_agent 的评估 prompt."""
    lines = [
        "# Meta-Evaluation Agent：综合评估报告生成",
        "",
        "你负责汇总各评分智能体的评估结果，生成面向学生的综合性形成性反馈报告。",
        "",
        "## 输入数据",
        "",
        "### 各维度评分",
        "```json",
        json.dumps(scores_detail, ensure_ascii=False, indent=2),
        "```",
        "",
        "### 协作指标（内部，不展示给学生）",
        f"- 协作综合分: {collaboration_score}",
        f"- 自评校准数据: {self_cal_data}",
        f"- 互评校准数据: {peer_cal_data}",
        "",
    ]

    if previous_rounds:
        lines.append("### 历史轮次（跨轮追踪）")
        lines.append("```json")
        lines.append(json.dumps(previous_rounds, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    lines.extend([
        "## 输出要求",
        "",
        "请生成 markdown 格式的综合反馈报告，包含以下部分：",
        "",
        "1. **总体评分**: 总分 + 各维度得分一览",
        "2. **各维度详细反馈**: 引用各 agent 的 feedback，给出改进建议",
        "3. **进步追踪**（如有历史数据）: 对比前几轮，指出进步与持续薄弱点",
        "4. **下一步建议**: 具体可行的行动建议",
        "",
        "⚠ 注意：协作分数为内部指标，不在报告中展示。",
    ])

    return "\n".join(lines)
