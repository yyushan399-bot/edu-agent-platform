"""元评估 Agent：整合 AI 评价、自评/互评校准与情绪分析，生成 Markdown 综合报告。"""

from __future__ import annotations

from typing import Any, TypedDict

from agents.emotion_agent import EmotionResult
from agents.peer_calibration_agent import PeerCalibrationResult
from agents.self_calibration_agent import SelfCalibrationResult

SELF_TYPE_LABELS: dict[str, str] = {
    "over_estimation": "高估型（自评系统性高于 AI 分数）",
    "under_estimation": "低估型（自评系统性低于 AI 分数）",
    "accurate": "校准较好（自评与 AI 分数接近）",
}

PEER_TYPE_LABELS: dict[str, str] = {
    "generous": "宽松型（互评分数系统性偏高）",
    "strict": "严格型（互评分数系统性偏低）",
    "objective": "客观型（互评与 AI 分数较为一致）",
}

EMOTION_LABELS: dict[str, str] = {
    "Overconfidence": "过度自信",
    "LowConfidence": "信心不足",
    "EvaluationAnxiety": "评价焦虑",
    "ReflectiveLearner": "反思型学习者",
}

ROUTE_LABELS: dict[str, str] = {
    "theory": "理论",
    "practice": "实践",
    "data": "数据分析",
    "literature": "文献阅读",
}


class MetaEvaluationResult(TypedDict):
    markdown: str


def _safe_str(value: object, default: str = "—") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _safe_float(value: object, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return default


def _performance_level(score: float | None) -> str:
    if score is None:
        return "暂无分数"
    if score >= 85:
        return "优秀"
    if score >= 70:
        return "良好"
    if score >= 60:
        return "基本达标"
    return "需加强"


def _format_score_detail(score_detail: object) -> str:
    if not isinstance(score_detail, dict):
        return "—"
    items = score_detail.get("items")
    if isinstance(items, list) and items:
        parts = []
        for item in items:
            if not isinstance(item, dict):
                continue
            label = item.get("label") or item.get("route") or "分项"
            score = _safe_float(item.get("score"))
            if score is not None:
                parts.append(f"{label} {score} 分")
        if parts:
            return "；".join(parts)
    scores = score_detail.get("scores")
    if isinstance(scores, dict) and scores:
        return "；".join(
            f"{ROUTE_LABELS.get(str(k), k)} {v} 分" for k, v in scores.items()
        )
    return "—"


def _section_learning_performance(ai: dict[str, Any]) -> str:
    total = _safe_float(ai.get("total_score"))
    route = _safe_str(ai.get("route") or _first_route(ai.get("routes")), "—")
    route_label = ROUTE_LABELS.get(route, route)
    level = _performance_level(total)
    feedback = _safe_str(ai.get("final_feedback"), "暂无 AI 综合反馈。")
    detail = _format_score_detail(ai.get("score_detail"))

    score_line = f"**综合得分**：{total} 分（{level}）" if total is not None else "**综合得分**：暂无"

    lines = [
        f"- {score_line}",
        f"- **评估路由**：{route_label}",
        f"- **分项得分**：{detail}",
        f"- **AI 综合反馈**：{feedback}",
    ]
    return "\n".join(lines)


def _first_route(routes: object) -> str:
    if isinstance(routes, list) and routes:
        return str(routes[0])
    return ""


def _section_self_calibration(self_cal: SelfCalibrationResult | dict[str, Any]) -> str:
    bias = _safe_float(self_cal.get("bias") if isinstance(self_cal, dict) else None)
    self_type = _safe_str(
        self_cal.get("self_type") if isinstance(self_cal, dict) else None,
        "accurate",
    )
    label = SELF_TYPE_LABELS.get(self_type, self_type)

    bias_line = f"{bias:+.1f} 分" if bias is not None else "—"
    analysis = _self_analysis_text(self_type, bias)

    return "\n".join(
        [
            f"- **自评偏差（self_score − ai_score）**：{bias_line}",
            f"- **自评类型**：{label}",
            f"- **分析**：{analysis}",
        ]
    )


def _self_analysis_text(self_type: str, bias: float | None) -> str:
    if self_type == "over_estimation":
        return (
            "您倾向于高估自己的表现，自评分数明显高于 AI 评估。"
            "建议在自评前先对照作业要求逐项检查，避免「感觉良好」替代证据。"
        )
    if self_type == "under_estimation":
        return (
            "您倾向于低估自己的表现，自评分数低于 AI 评估。"
            "建议记录已完成的具体成果与正确要点，建立对能力的客观认识。"
        )
    return (
        "自评与 AI 分数较为接近，具备较好的自我校准能力。"
        "可继续保持「先自评、后对照反馈」的习惯。"
    )


def _section_peer_calibration(peer_cal: PeerCalibrationResult | dict[str, Any]) -> str:
    peer_bias = _safe_float(peer_cal.get("peer_bias") if isinstance(peer_cal, dict) else None)
    peer_type = _safe_str(
        peer_cal.get("peer_type") if isinstance(peer_cal, dict) else None,
        "objective",
    )
    count = peer_cal.get("count") if isinstance(peer_cal, dict) else 0
    try:
        count = int(count or 0)
    except (TypeError, ValueError):
        count = 0

    label = PEER_TYPE_LABELS.get(peer_type, peer_type)
    bias_line = f"{peer_bias:+.1f} 分" if peer_bias is not None else "—"
    analysis = _peer_analysis_text(peer_type, peer_bias, count)

    return "\n".join(
        [
            f"- **互评偏差（peer_score − ai_score 均值）**：{bias_line}",
            f"- **互评类型**：{label}",
            f"- **样本数量**：{count} 次互评",
            f"- **分析**：{analysis}",
        ]
    )


def _peer_analysis_text(peer_type: str, peer_bias: float | None, count: int) -> str:
    if count == 0:
        return "暂无互评记录，暂无法分析互评倾向；完成同伴互评后可更新本项分析。"
    if peer_type == "generous":
        return (
            "您在互评中整体给分偏高，可能对同伴较为宽松。"
            "建议互评时引用具体证据，并对照评分标准区分「完成」与「优秀」。"
        )
    if peer_type == "strict":
        return (
            "您在互评中整体给分偏低，评价标准可能偏严。"
            "建议在指出不足的同时，明确肯定已达标的部分，保持建设性反馈。"
        )
    return (
        "互评分数与 AI 评估整体较为一致，评价尺度相对客观。"
        "可继续以「具体事例 + 改进建议」的方式提供互评。"
    )


def _section_emotion(emotion: EmotionResult | dict[str, Any]) -> str:
    state = _safe_str(
        emotion.get("emotion_state") if isinstance(emotion, dict) else None,
        "ReflectiveLearner",
    )
    reason = _safe_str(
        emotion.get("emotion_reason") if isinstance(emotion, dict) else None,
        "暂无情绪分析依据。",
    )
    label = EMOTION_LABELS.get(state, state)
    analysis = _emotion_analysis_text(state)

    return "\n".join(
        [
            f"- **情绪状态**：{label}（`{state}`）",
            f"- **判断依据**：{reason}",
            f"- **分析**：{analysis}",
        ]
    )


def _emotion_analysis_text(state: str) -> str:
    mapping = {
        "Overconfidence": (
            "在评价情境中表现出较强自信，需警惕与真实表现之间的落差，"
            "避免过度自信影响后续学习投入。"
        ),
        "LowConfidence": (
            "在评价情境中信心不足，可能低估已有能力；"
            "建议通过小步验证与正向反馈逐步建立自我效能感。"
        ),
        "EvaluationAnxiety": (
            "对评价过程存在焦虑或压力，可能影响自评与互评的稳定性；"
            "建议将关注点从「分数本身」转向「可改进的具体行为」。"
        ),
        "ReflectiveLearner": (
            "能够对照反馈进行反思，情绪与评价行为整体较为健康；"
            "适合作为小组中的反思与总结推动者。"
        ),
    }
    return mapping.get(state, mapping["ReflectiveLearner"])


def _build_suggestions(
    ai: dict[str, Any],
    self_cal: dict[str, Any],
    peer_cal: dict[str, Any],
    emotion: dict[str, Any],
) -> str:
    suggestions: list[str] = []

    total = _safe_float(ai.get("total_score"))
    if total is not None and total < 70:
        suggestions.append(
            "针对 AI 指出的薄弱项制定下一周学习计划，优先补齐影响综合得分的关键维度。"
        )
    elif total is not None and total >= 85:
        suggestions.append(
            "在保持现有优势的同时，尝试挑战更高阶任务（如延伸论证、跨文献比较或方法改进）。"
        )

    self_type = self_cal.get("self_type", "accurate")
    if self_type == "over_estimation":
        suggestions.append(
            "自评时使用检查清单：逐条对照作业要求后再打分，避免一次性给出「整体感觉分」。"
        )
    elif self_type == "under_estimation":
        suggestions.append(
            "建立「成就日志」，记录每次作业中已被 AI 或同伴肯定的要点，再与自评对照。"
        )
    else:
        suggestions.append(
            "保持当前自评校准习惯，可在每次提交前用 1～2 句话说明自评依据。"
        )

    peer_type = peer_cal.get("peer_type", "objective")
    count = peer_cal.get("count") or 0
    if count == 0:
        suggestions.append("主动参与同伴互评，通过评价他人来训练自身的评价标准与反馈能力。")
    elif peer_type == "generous":
        suggestions.append(
            "互评时采用「证据—标准—建议」三段式：先引用原文/操作，再对照 rubric，最后给出可执行建议。"
        )
    elif peer_type == "strict":
        suggestions.append(
            "互评反馈采用「1 条肯定 + 1 条改进」结构，避免只指出问题而削弱同伴的学习动机。"
        )
    else:
        suggestions.append(
            "继续以客观尺度进行互评，可尝试与 AI 分数对照，检验自身评价一致性。"
        )

    emotion_state = emotion.get("emotion_state", "ReflectiveLearner")
    if emotion_state == "Overconfidence":
        suggestions.append(
            "收到 AI 反馈后，强制列出至少 2 条「与预期不符」的具体意见并制定改进行动。"
        )
    elif emotion_state == "LowConfidence":
        suggestions.append(
            "将大目标拆分为可在一周内完成的小任务，每完成一项即记录进展以积累成功体验。"
        )
    elif emotion_state == "EvaluationAnxiety":
        suggestions.append(
            "采用「草稿—自评—修改—提交」流程，在正式评价前完成一轮自我修订以降低焦虑。"
        )
    else:
        suggestions.append(
            "延续反思型学习策略：每次评价后写 3 行复盘（收获 / 不足 / 下次行动）。"
        )

    return "\n".join(f"{i}. {s}" for i, s in enumerate(suggestions, start=1))


def generate_meta_evaluation_markdown(
    ai_evaluation: dict[str, Any],
    self_calibration: SelfCalibrationResult | dict[str, Any],
    peer_calibration: PeerCalibrationResult | dict[str, Any],
    emotion: EmotionResult | dict[str, Any],
    *,
    title: str = "综合元评估报告",
) -> str:
    """生成 Markdown 格式元评估报告。"""
    ai = dict(ai_evaluation or {})
    self_cal = dict(self_calibration or {})
    peer_cal = dict(peer_calibration or {})
    emotion_data = dict(emotion or {})

    sections = [
        f"# {title}",
        "",
        "## 1. 学习表现分析",
        "",
        _section_learning_performance(ai),
        "",
        "## 2. 自评能力分析",
        "",
        _section_self_calibration(self_cal),
        "",
        "## 3. 互评能力分析",
        "",
        _section_peer_calibration(peer_cal),
        "",
        "## 4. 情感状态分析",
        "",
        _section_emotion(emotion_data),
        "",
        "## 5. 改进建议",
        "",
        _build_suggestions(ai, self_cal, peer_cal, emotion_data),
        "",
    ]
    return "\n".join(sections)


class MetaEvaluationAgent:
    """元评估 Agent 门面。"""

    def run(
        self,
        ai_evaluation: dict[str, Any],
        self_calibration: SelfCalibrationResult | dict[str, Any],
        peer_calibration: PeerCalibrationResult | dict[str, Any],
        emotion: EmotionResult | dict[str, Any],
        *,
        title: str = "综合元评估报告",
    ) -> MetaEvaluationResult:
        markdown = generate_meta_evaluation_markdown(
            ai_evaluation,
            self_calibration,
            peer_calibration,
            emotion,
            title=title,
        )
        return {"markdown": markdown}


__all__ = [
    "MetaEvaluationAgent",
    "MetaEvaluationResult",
    "generate_meta_evaluation_markdown",
]
