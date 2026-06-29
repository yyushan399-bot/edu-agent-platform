"""互评校准 Agent：对比同伴评分与 AI 分数，判断宽松/严格/客观。"""

from __future__ import annotations

from typing import Literal, TypedDict

PeerType = Literal["generous", "strict", "objective"]

BIAS_THRESHOLD = 0.75


class PeerCalibrationResult(TypedDict):
    peer_bias: float
    peer_type: PeerType
    count: int


def _clamp_score(value: float) -> float:
    return float(max(1.0, min(5.0, round(float(value), 2))))


def classify_peer_type(bias: float, *, threshold: float = BIAS_THRESHOLD) -> PeerType:
    """
    根据互评偏差分类评价倾向（1-5 分制）。

    - bias > threshold  → generous（宽松，给分偏高）
    - bias < -threshold → strict（严格，给分偏低）
    - 否则              → objective（较客观）
    """
    if bias > threshold:
        return "generous"
    if bias < -threshold:
        return "strict"
    return "objective"


def compute_peer_bias(peer_scores: list[float], ai_scores: list[float]) -> float:
    """
    计算平均互评偏差（输入分数均为 1-5 分制）。

    对每一对：bias_i = peer_score_i - ai_score_i
    peer_bias = mean(bias_i)
    """
    if len(peer_scores) != len(ai_scores):
        raise ValueError(
            f"peer_scores 与 ai_scores 长度须一致，"
            f"got {len(peer_scores)} vs {len(ai_scores)}"
        )
    if not peer_scores:
        raise ValueError("peer_scores 与 ai_scores 不能为空")

    biases = [
        _clamp_score(peer) - _clamp_score(ai)
        for peer, ai in zip(peer_scores, ai_scores, strict=True)
    ]
    return round(sum(biases) / len(biases), 2)


def calibrate_peer_scores(
    peer_scores: list[float],
    ai_scores: list[float],
    *,
    threshold: float = BIAS_THRESHOLD,
) -> PeerCalibrationResult:
    """
    根据多组互评与 AI 分数计算 peer_bias 并分类（1-5 分制）。

    peer_bias = mean(peer_score - ai_score)

    - peer_bias > 0.75  → generous（宽松，给分偏高）
    - peer_bias < -0.75 → strict（严格，给分偏低）
    - 否则              → objective（较客观）
    """
    peer_bias = compute_peer_bias(peer_scores, ai_scores)
    peer_type = classify_peer_type(peer_bias, threshold=threshold)
    return {
        "peer_bias": peer_bias,
        "peer_type": peer_type,
        "count": len(peer_scores),
    }


class PeerCalibrationAgent:
    """互评校准 Agent 门面。"""

    def __init__(self, *, threshold: float = BIAS_THRESHOLD) -> None:
        self.threshold = threshold

    def run(
        self,
        peer_scores: list[float],
        ai_scores: list[float],
    ) -> PeerCalibrationResult:
        return calibrate_peer_scores(
            peer_scores,
            ai_scores,
            threshold=self.threshold,
        )


__all__ = [
    "BIAS_THRESHOLD",
    "PeerCalibrationAgent",
    "PeerCalibrationResult",
    "PeerType",
    "calibrate_peer_scores",
    "classify_peer_type",
    "compute_peer_bias",
]
