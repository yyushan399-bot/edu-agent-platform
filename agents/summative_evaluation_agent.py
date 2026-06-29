"""终结性评价智能体：接收自评 / 互评 / 智能体分数，生成协作能力终结性评价。"""

from __future__ import annotations

import json
from typing import Any, TypedDict

from agents.peer_calibration_agent import calibrate_peer_scores
from agents.self_calibration_agent import calibrate_self_score

DEFAULT_WEIGHTS: dict[str, float] = {
    "ai_score": 0.40,
    "self_score": 0.30,
    "peer_score": 0.30,
}


class SummativeEvaluationResult(TypedDict):
    collaboration_scores: dict[str, Any]
    self_calibration: dict[str, Any]
    peer_calibration: dict[str, Any]
    collaboration_score: float | None
    summative_score: float | None
    summative_comment: str
    collaboration_analysis: str
    missing_scores: list[str]
    weights_used: dict[str, float]


def _clamp_score(value: float) -> float:
    return float(max(0.0, min(100.0, round(float(value), 2))))


def compute_weighted_collaboration_score(
    *,
    ai_score: float | None,
    self_score: float | None,
    peer_score: float | None,
    weights: dict[str, float] | None = None,
) -> tuple[float | None, dict[str, float]]:
    """按可用分数与权重计算协作能力综合分。"""
    weight_map = dict(weights or DEFAULT_WEIGHTS)
    pairs = [
        ("ai_score", ai_score),
        ("self_score", self_score),
        ("peer_score", peer_score),
    ]
    active = [(key, val) for key, val in pairs if val is not None]
    if not active:
        return None, {}

    total_weight = sum(weight_map.get(key, 0.0) for key, _ in active)
    if total_weight <= 0:
        equal = 1.0 / len(active)
        used = {key: equal for key, _ in active}
    else:
        used = {key: weight_map.get(key, 0.0) / total_weight for key, _ in active}

    composite = sum(val * used[key] for key, val in active)
    return _clamp_score(composite), used


def _build_rule_based_comment(
    *,
    collaboration_score: float | None,
    ai_score: float | None,
    self_score: float | None,
    peer_score: float | None,
    self_calibration: dict[str, Any],
    peer_calibration: dict[str, Any],
    missing_scores: list[str],
) -> tuple[str, str]:
    parts: list[str] = []
    analysis_parts: list[str] = []

    if collaboration_score is not None:
        parts.append(f"协作能力综合得分 {collaboration_score:.1f}/100。")
    if ai_score is not None:
        analysis_parts.append(f"智能体评估 {ai_score:.1f} 分")
    if self_score is not None:
        analysis_parts.append(f"自评 {self_score:.1f} 分")
    if peer_score is not None:
        analysis_parts.append(f"互评均值 {peer_score:.1f} 分")

    self_type = self_calibration.get("self_type")
    if self_type == "over_estimation":
        analysis_parts.append("自评略高于智能体分数，建议加强证据对照")
    elif self_type == "under_estimation":
        analysis_parts.append("自评低于智能体分数，可更客观认识已有成果")
    elif self_score is not None and ai_score is not None:
        analysis_parts.append("自评与智能体分数较为接近")

    peer_type = peer_calibration.get("peer_type")
    peer_count = int(peer_calibration.get("count") or 0)
    if peer_count == 0:
        analysis_parts.append("尚无互评记录")
    elif peer_type == "generous":
        analysis_parts.append("同伴评分整体高于智能体评估")
    elif peer_type == "strict":
        analysis_parts.append("同伴评分整体低于智能体评估")
    elif peer_score is not None:
        analysis_parts.append("同伴评分与智能体评估较为一致")

    if missing_scores:
        missing_label = "、".join(missing_scores)
        parts.append(f"当前缺少 {missing_label}，终结性评价基于已有数据生成。")

    collaboration_analysis = "；".join(analysis_parts) + "。" if analysis_parts else "暂无足够数据。"
    summative_comment = " ".join(parts) + " " + collaboration_analysis
    return summative_comment.strip(), collaboration_analysis


def _build_llm_comment(payload: dict[str, Any]) -> str | None:
    try:
        import llm_config  # noqa: F401
        from langchain_core.prompts import ChatPromptTemplate
        from llm_config import get_chat_llm
        from pydantic import BaseModel, Field
    except Exception:
        return None

    class SummativeOutput(BaseModel):
        summative_comment: str = Field(description="面向学生的终结性评价与协作能力总结")
        collaboration_analysis: str = Field(description="对自评/互评/智能体分数关系的简要分析")

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是教育评估终结性评价专家。你将收到反映学生协作能力的三类分数："
                "智能体评估分（客观作业质量）、自评分、互评均值。"
                "请基于分数与校准信息，生成简洁、可操作的终结性评价。"
                "只输出 JSON，包含 summative_comment 与 collaboration_analysis。",
            ),
            (
                "human",
                "协作能力输入（JSON）：\n{payload_json}",
            ),
        ]
    )

    llm = get_chat_llm(temperature=0.3)
    structured = llm.with_structured_output(SummativeOutput, method="json_mode")
    chain = prompt | structured
    try:
        result = chain.invoke(
            {"payload_json": json.dumps(payload, ensure_ascii=False, indent=2)}
        )
        return str(result.summative_comment).strip()
    except Exception:
        return None


def run_summative_evaluation(
    collaboration: dict[str, Any],
    *,
    weights: dict[str, float] | None = None,
    use_llm: bool = True,
) -> SummativeEvaluationResult:
    """
    将自评 / 互评 / 智能体分数送入终结性评价智能体。

    collaboration 需包含 ai_score、self_score、peer_score（均可选，但至少需 ai_score）。
    """
    ai_score = collaboration.get("ai_score")
    self_score = collaboration.get("self_score")
    peer_score = collaboration.get("peer_score")
    peer_scores = list(collaboration.get("peer_scores") or [])
    missing_scores = list(collaboration.get("missing_scores") or [])

    if ai_score is not None:
        ai_score = _clamp_score(float(ai_score))
    if self_score is not None:
        self_score = _clamp_score(float(self_score))
    if peer_score is not None:
        peer_score = _clamp_score(float(peer_score))

    self_calibration: dict[str, Any] = {"bias": None, "self_type": "accurate"}
    if ai_score is not None and self_score is not None:
        self_calibration = dict(calibrate_self_score(ai_score, self_score))

    peer_calibration: dict[str, Any] = {
        "peer_bias": None,
        "peer_type": "objective",
        "count": len(peer_scores),
    }
    if ai_score is not None and peer_scores:
        peer_calibration = dict(
            calibrate_peer_scores(peer_scores, [ai_score] * len(peer_scores))
        )

    collaboration_score, weights_used = compute_weighted_collaboration_score(
        ai_score=ai_score,
        self_score=self_score,
        peer_score=peer_score,
        weights=weights,
    )

    collaboration_scores = {
        "ai_score": ai_score,
        "self_score": self_score,
        "peer_score": peer_score,
        "peer_review_count": int(collaboration.get("peer_review_count") or len(peer_scores)),
        "self_comment": collaboration.get("self_comment"),
    }

    llm_payload = {
        "collaboration_scores": collaboration_scores,
        "self_calibration": self_calibration,
        "peer_calibration": peer_calibration,
        "collaboration_score": collaboration_score,
        "missing_scores": missing_scores,
        "user_id": collaboration.get("user_id"),
        "assignment_id": collaboration.get("assignment_id"),
    }

    rule_comment, rule_analysis = _build_rule_based_comment(
        collaboration_score=collaboration_score,
        ai_score=ai_score,
        self_score=self_score,
        peer_score=peer_score,
        self_calibration=self_calibration,
        peer_calibration=peer_calibration,
        missing_scores=missing_scores,
    )

    summative_comment = rule_comment
    collaboration_analysis = rule_analysis
    if use_llm:
        llm_comment = _build_llm_comment(llm_payload)
        if llm_comment:
            summative_comment = llm_comment

    summative_score = collaboration_score

    return {
        "collaboration_scores": collaboration_scores,
        "self_calibration": self_calibration,
        "peer_calibration": peer_calibration,
        "collaboration_score": collaboration_score,
        "summative_score": summative_score,
        "summative_comment": summative_comment,
        "collaboration_analysis": collaboration_analysis,
        "missing_scores": missing_scores,
        "weights_used": weights_used,
    }


class SummativeEvaluationAgent:
    """终结性评价 Agent 门面。"""

    def run(
        self,
        collaboration: dict[str, Any],
        *,
        weights: dict[str, float] | None = None,
        use_llm: bool = True,
    ) -> SummativeEvaluationResult:
        return run_summative_evaluation(
            collaboration,
            weights=weights,
            use_llm=use_llm,
        )


__all__ = [
    "DEFAULT_WEIGHTS",
    "SummativeEvaluationAgent",
    "SummativeEvaluationResult",
    "compute_weighted_collaboration_score",
    "run_summative_evaluation",
]
