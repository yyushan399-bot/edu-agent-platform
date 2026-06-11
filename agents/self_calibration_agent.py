"""自评校准 Agent：对比 AI 分数与自评分数，判断高估/低估/准确。"""

from __future__ import annotations

from typing import Literal, TypedDict

SelfType = Literal["over_estimation", "under_estimation", "accurate"]

BIAS_THRESHOLD = 15.0


class SelfCalibrationResult(TypedDict):
    bias: float
    self_type: SelfType


def _clamp_score(value: float) -> float:
    return float(max(0.0, min(100.0, round(float(value), 2))))


def classify_self_type(bias: float, *, threshold: float = BIAS_THRESHOLD) -> SelfType:
    """根据偏差值分类自评类型。"""
    if bias > threshold:
        return "over_estimation"
    if bias < -threshold:
        return "under_estimation"
    return "accurate"


def calibrate_self_score(
    ai_score: float,
    self_score: float,
    *,
    threshold: float = BIAS_THRESHOLD,
) -> SelfCalibrationResult:
    """
    计算自评偏差并返回校准结果。

    bias = self_score - ai_score

    - bias > 15  → over_estimation（高估）
    - bias < -15 → under_estimation（低估）
    - 否则       → accurate（较准确）
    """
    ai = _clamp_score(ai_score)
    self_val = _clamp_score(self_score)
    bias = round(self_val - ai, 2)
    self_type = classify_self_type(bias, threshold=threshold)
    return {"bias": bias, "self_type": self_type}


class SelfCalibrationAgent:
    """自评校准 Agent 门面。"""

    def __init__(self, *, threshold: float = BIAS_THRESHOLD) -> None:
        self.threshold = threshold

    def run(self, ai_score: float, self_score: float) -> SelfCalibrationResult:
        return calibrate_self_score(
            ai_score,
            self_score,
            threshold=self.threshold,
        )


__all__ = [
    "BIAS_THRESHOLD",
    "SelfCalibrationAgent",
    "SelfCalibrationResult",
    "SelfType",
    "calibrate_self_score",
    "classify_self_type",
]
