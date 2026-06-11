"""情绪识别 Agent：根据自评/互评偏差历史与文本评论推断学习情绪状态。"""

from __future__ import annotations

import math
from typing import Literal, TypedDict

EmotionState = Literal[
    "Overconfidence",
    "LowConfidence",
    "EvaluationAnxiety",
    "ReflectiveLearner",
]

BIAS_THRESHOLD = 15.0
CALIBRATED_THRESHOLD = 10.0
VOLATILITY_THRESHOLD = 12.0

# 评论关键词（中英）
_OVERCONFIDENCE_KEYWORDS = (
    "自信", "肯定", "没问题", "很好", "完全", "一定", "擅长", "优秀",
    "confident", "sure", "perfect", "excellent", "definitely",
)
_LOW_CONFIDENCE_KEYWORDS = (
    "不确定", "没把握", "不够好", "不太行", "可能错", "担心", "薄弱",
    "unsure", "not sure", "maybe wrong", "not good enough", "weak",
)
_ANXIETY_KEYWORDS = (
    "紧张", "焦虑", "害怕", "压力", "不安", "慌", "担心被", "评卷",
    "anxious", "anxiety", "nervous", "stress", "worried", "afraid",
)
_REFLECTIVE_KEYWORDS = (
    "反思", "改进", "学习", "总结", "下次", "意识到", "对照", "不足",
    "提升", "复盘", "收获", "reflect", "improve", "learn", "summary",
)


class EmotionResult(TypedDict):
    emotion_state: EmotionState
    emotion_reason: str


class _EmotionScores(TypedDict):
    Overconfidence: float
    LowConfidence: float
    EvaluationAnxiety: float
    ReflectiveLearner: float


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = _mean(values)
    variance = sum((v - avg) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def _normalize_comments(comments: list[str]) -> str:
    parts = [(c or "").strip() for c in comments if (c or "").strip()]
    return "\n".join(parts).lower()


def _count_keyword_hits(text: str, keywords: tuple[str, ...]) -> int:
    if not text:
        return 0
    hits = 0
    for kw in keywords:
        if kw.lower() in text:
            hits += 1
    return hits


def _score_emotions(
    *,
    self_mean: float,
    self_std: float,
    peer_mean: float,
    comment_text: str,
) -> _EmotionScores:
    scores: _EmotionScores = {
        "Overconfidence": 0.0,
        "LowConfidence": 0.0,
        "EvaluationAnxiety": 0.0,
        "ReflectiveLearner": 10.0,
    }

    # --- Overconfidence ---
    if self_mean > BIAS_THRESHOLD:
        scores["Overconfidence"] += 45
    elif self_mean > CALIBRATED_THRESHOLD:
        scores["Overconfidence"] += 25
    scores["Overconfidence"] += min(
        30, _count_keyword_hits(comment_text, _OVERCONFIDENCE_KEYWORDS) * 12
    )

    # --- LowConfidence ---
    if self_mean < -BIAS_THRESHOLD:
        scores["LowConfidence"] += 45
    elif self_mean < -CALIBRATED_THRESHOLD:
        scores["LowConfidence"] += 25
    scores["LowConfidence"] += min(
        30, _count_keyword_hits(comment_text, _LOW_CONFIDENCE_KEYWORDS) * 12
    )

    # --- EvaluationAnxiety ---
    if self_std >= VOLATILITY_THRESHOLD:
        scores["EvaluationAnxiety"] += 35
    elif self_std >= 8.0:
        scores["EvaluationAnxiety"] += 18
    anxiety_kw = _count_keyword_hits(comment_text, _ANXIETY_KEYWORDS)
    scores["EvaluationAnxiety"] += min(40, anxiety_kw * 15)
    if peer_mean <= -CALIBRATED_THRESHOLD and self_std >= 8.0:
        scores["EvaluationAnxiety"] += 12

    # --- ReflectiveLearner ---
    if abs(self_mean) <= CALIBRATED_THRESHOLD:
        scores["ReflectiveLearner"] += 30
    if abs(peer_mean) <= CALIBRATED_THRESHOLD:
        scores["ReflectiveLearner"] += 15
    scores["ReflectiveLearner"] += min(
        35, _count_keyword_hits(comment_text, _REFLECTIVE_KEYWORDS) * 12
    )
    if (
        abs(self_mean) <= CALIBRATED_THRESHOLD
        and _count_keyword_hits(comment_text, _REFLECTIVE_KEYWORDS) > 0
    ):
        scores["ReflectiveLearner"] += 10

    return scores


def _pick_emotion(scores: _EmotionScores) -> EmotionState:
    order: tuple[EmotionState, ...] = (
        "EvaluationAnxiety",
        "Overconfidence",
        "LowConfidence",
        "ReflectiveLearner",
    )
    best = max(scores.values())
    for state in order:
        if scores[state] == best:
            return state
    return "ReflectiveLearner"


def _build_reason(
    emotion: EmotionState,
    *,
    self_mean: float,
    self_std: float,
    peer_mean: float,
    comment_text: str,
    self_count: int,
    peer_count: int,
) -> str:
    parts: list[str] = []

    if self_count:
        parts.append(f"自评偏差历史均值 {self_mean:+.1f}")
        if self_std >= 8.0:
            parts.append(f"波动标准差 {self_std:.1f}")
    if peer_count:
        parts.append(f"互评偏差历史均值 {peer_mean:+.1f}")

    if emotion == "Overconfidence":
        if self_mean > CALIBRATED_THRESHOLD:
            parts.append("自评持续高于 AI 分数，存在高估倾向")
        if _count_keyword_hits(comment_text, _OVERCONFIDENCE_KEYWORDS):
            parts.append("评论中出现较强自信表述")
    elif emotion == "LowConfidence":
        if self_mean < -CALIBRATED_THRESHOLD:
            parts.append("自评持续低于 AI 分数，存在低估倾向")
        if _count_keyword_hits(comment_text, _LOW_CONFIDENCE_KEYWORDS):
            parts.append("评论中表现出对自身能力的不确定")
    elif emotion == "EvaluationAnxiety":
        if self_std >= VOLATILITY_THRESHOLD:
            parts.append("自评偏差波动较大，评价情绪不稳定")
        if _count_keyword_hits(comment_text, _ANXIETY_KEYWORDS):
            parts.append("评论中提及紧张、焦虑或评价压力")
        if peer_mean <= -CALIBRATED_THRESHOLD:
            parts.append("互评偏严格可能加剧评价焦虑")
    else:
        if abs(self_mean) <= CALIBRATED_THRESHOLD:
            parts.append("自评与 AI 分数较为一致")
        if _count_keyword_hits(comment_text, _REFLECTIVE_KEYWORDS):
            parts.append("评论中包含反思、改进或学习总结")

    if not parts:
        return "历史与评论信号较弱，暂归类为反思型学习者，建议持续观察。"

    return "；".join(parts) + "。"


def analyze_emotion(
    self_bias_history: list[float],
    peer_bias_history: list[float],
    comments: list[str],
) -> EmotionResult:
    """
    根据偏差历史与评论文本推断情绪状态。

    可能结果：
    - Overconfidence：自评系统性偏高 / 过度自信
    - LowConfidence：自评系统性偏低 / 信心不足
    - EvaluationAnxiety：评价波动大或表达焦虑
    - ReflectiveLearner：自评较校准且具反思性
    """
    self_mean = round(_mean(self_bias_history), 2)
    self_std = round(_std(self_bias_history), 2)
    peer_mean = round(_mean(peer_bias_history), 2)
    comment_text = _normalize_comments(comments)

    scores = _score_emotions(
        self_mean=self_mean,
        self_std=self_std,
        peer_mean=peer_mean,
        comment_text=comment_text,
    )
    emotion_state = _pick_emotion(scores)
    emotion_reason = _build_reason(
        emotion_state,
        self_mean=self_mean,
        self_std=self_std,
        peer_mean=peer_mean,
        comment_text=comment_text,
        self_count=len(self_bias_history),
        peer_count=len(peer_bias_history),
    )

    return {
        "emotion_state": emotion_state,
        "emotion_reason": emotion_reason,
    }


class EmotionAgent:
    """情绪识别 Agent 门面。"""

    def run(
        self,
        self_bias_history: list[float],
        peer_bias_history: list[float],
        comments: list[str],
    ) -> EmotionResult:
        return analyze_emotion(
            self_bias_history,
            peer_bias_history,
            comments,
        )


__all__ = [
    "EmotionAgent",
    "EmotionResult",
    "EmotionState",
    "analyze_emotion",
]
