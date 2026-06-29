"""按章节评分智能体（学生反馈 · 阶段 0 迁入）。"""

from __future__ import annotations

import statistics
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from agents.group_project.pbl_config import DEFAULT_MODEL, DEFAULT_SCORING_TIMES
from agents.group_project.scoring_models import DeepSeekClient
from agents.group_project.scoring_utils import judge_consistency
from agents.section_report.section_config import SECTION_NAMES
from services.section_graphrag_service import GraphRAGRetriever

__all__ = [
    "CriterionScore",
    "CriterionSummary",
    "DeepSeekClient",
    "GraphRAGRetriever",
    "DEFAULT_MODEL",
    "DEFAULT_SCORING_TIMES",
    "SECTION_NAMES",
    "build_section_scoring_prompt",
    "rescore_criteria",
    "score_criteria",
    "score_single_criterion",
]


class CriterionScore(BaseModel):
    score: int = Field(..., ge=1, le=5)
    reason: str
    evidence: list[str] = Field(default_factory=list)
    reference_comparison: str = ""
    weakness: str = ""
    suggestion: str = ""


class CriterionSummary(BaseModel):
    criterion_name: str
    weight: float
    scores: list[CriterionScore]
    mean: float
    std: float
    cv: float | None
    min_score: float
    max_score: float
    consistency_level: str
    summary_reason: str = ""
    summary_evidence: list[str] = Field(default_factory=list)


def build_section_scoring_prompt(
    section_name: str,
    criterion_name: str,
    weight: float,
    rubrics: dict[int, str],
    exemplars: dict[int, list[dict[str, Any]]],
    student_text: str,
    round_index: int,
    audit_feedback: str | None = None,
) -> tuple[str, str]:
    rubric_lines = [
        f"{score}分：{rubrics[score]}"
        for score in sorted(rubrics.keys(), reverse=True)
    ]

    exemplar_lines: list[str] = []
    for score in sorted(exemplars.keys(), reverse=True):
        examples = exemplars[score]
        if not examples:
            continue
        exemplar_lines.append(f"\n【{score}分参考范例】")
        for i, ex in enumerate(examples[:2], 1):
            content = ex["content"]
            content_preview = content[:400] if len(content) > 400 else content
            exemplar_lines.append(
                f"  范例{i}（来自{ex['source_report']}，{ex['quality_tag']}）："
            )
            exemplar_lines.append(f"  {content_preview}")
            if ex.get("reason"):
                exemplar_lines.append(f"  标注理由：{ex['reason'][:200]}")

    system_prompt = f"""你是一名资深 STEM 教育评估专家，精通项目化学习研究报告的评分。

当前任务：对学生报告的【{section_name}】章节中的【{criterion_name}】指标进行评分。

评分原则：
1. 评分范围：1-5 分整数
2. 必须基于学生实际文本评分，不能编造或推测
3. 参考范例只用于理解不同分值的质量差异，不能把范例内容当作学生表现
4. evidence 必须引用学生原文中的具体句子
5. 本次是第 {round_index} 次独立评分，请独立判断
6. 如果学生文本中没有体现该指标，应明确指出缺失，给低分"""

    if audit_feedback:
        system_prompt += f"""

【重要：上次审核未通过，请根据以下反馈修正评分】
{audit_feedback}
请特别注意：evidence 必须直接来自学生文本，不可杜撰；评分理由与量规描述保持一致。"""

    user_prompt = f"""## 评分指标：{criterion_name}（权重 {weight}）

### 量规描述（1-5分）
{"\n".join(rubric_lines)}

### 参考范例（仅用于质量对照）
{"\n".join(exemplar_lines) if exemplar_lines else "[该指标暂无参考范例]"}

### 学生实际文本（【{section_name}】章节）
{student_text[:3000]}


### 评分任务
请根据量规和参考范例，对学生文本在该指标上的表现进行评分。

请严格输出以下 JSON 格式：
{{
  "score": 整数(1-5),
  "reason": "评分理由",
  "evidence": ["支持你打分的学生原文片段1", "学生原文片段2"],
  "reference_comparison": "与参考范例的质量对比（仅用于尺度校准，不引用范例原文）",
  "weakness": "该指标的主要不足",
  "suggestion": "具体改进建议"
}}
""".strip()
    return system_prompt.strip(), user_prompt


def score_single_criterion(
    llm: DeepSeekClient,
    section_name: str,
    criterion_name: str,
    weight: float,
    rubrics: dict[int, str],
    exemplars: dict[int, list[dict[str, Any]]],
    student_text: str,
    scoring_times: int = DEFAULT_SCORING_TIMES,
    audit_feedback: str | None = None,
) -> CriterionSummary:
    scores: list[CriterionScore] = []
    for i in range(1, scoring_times + 1):
        system_prompt, user_prompt = build_section_scoring_prompt(
            section_name=section_name,
            criterion_name=criterion_name,
            weight=weight,
            rubrics=rubrics,
            exemplars=exemplars,
            student_text=student_text,
            round_index=i,
            audit_feedback=audit_feedback,
        )
        raw = llm.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.0,
        )
        try:
            parsed = CriterionScore(**raw)
        except ValidationError:
            fixed = {
                "score": max(1, min(5, int(raw.get("score", 3)))),
                "reason": str(raw.get("reason", "")),
                "evidence": raw.get("evidence", [])
                if isinstance(raw.get("evidence"), list)
                else [str(raw.get("evidence", ""))],
                "reference_comparison": str(raw.get("reference_comparison", "")),
                "weakness": str(raw.get("weakness", "")),
                "suggestion": str(raw.get("suggestion", "")),
            }
            parsed = CriterionScore(**fixed)
        scores.append(parsed)

    numeric_scores = [s.score for s in scores]
    mean = float(statistics.fmean(numeric_scores))
    std = float(statistics.pstdev(numeric_scores)) if len(numeric_scores) > 1 else 0.0
    cv = std / mean if mean > 1e-8 else None
    min_score = float(min(numeric_scores))
    max_score = float(max(numeric_scores))
    consistency = judge_consistency(cv, std, min_score, max_score)

    reason_counts: dict[str, int] = {}
    for s in scores:
        reason_counts[s.reason] = reason_counts.get(s.reason, 0) + 1
    summary_reason = max(reason_counts, key=reason_counts.get) if reason_counts else ""

    all_evidence: list[str] = []
    for s in scores:
        all_evidence.extend(s.evidence)
    summary_evidence = list(dict.fromkeys(all_evidence))[:5]

    return CriterionSummary(
        criterion_name=criterion_name,
        weight=weight,
        scores=scores,
        mean=round(mean, 3),
        std=round(std, 3),
        cv=round(cv, 3) if cv is not None else None,
        min_score=round(min_score, 3),
        max_score=round(max_score, 3),
        consistency_level=consistency,
        summary_reason=summary_reason,
        summary_evidence=summary_evidence,
    )


def score_criteria(
    llm: DeepSeekClient,
    retriever: GraphRAGRetriever,
    section_name: str,
    student_text: str,
    criteria_names: list[str] | None = None,
    scoring_times: int = DEFAULT_SCORING_TIMES,
) -> dict[str, CriterionSummary]:
    context = retriever.retrieve_full_context(section_name)
    all_criteria = context["criteria"]

    if criteria_names is None:
        target_criteria = all_criteria
    else:
        target_criteria = [
            c for c in all_criteria if c["criterion_name"] in criteria_names
        ]
        missing = set(criteria_names) - {c["criterion_name"] for c in target_criteria}
        if missing:
            raise ValueError(f"未找到指标：{missing}")

    results: dict[str, CriterionSummary] = {}
    for crit in target_criteria:
        print(f"  评分指标：{crit['criterion_name']}...")
        summary = score_single_criterion(
            llm=llm,
            section_name=section_name,
            criterion_name=crit["criterion_name"],
            weight=crit["weight"],
            rubrics=crit["rubrics"],
            exemplars=crit["exemplars"],
            student_text=student_text,
            scoring_times=scoring_times,
        )
        results[crit["criterion_name"]] = summary
        print(
            f"    完成：mean={summary.mean}, std={summary.std}, "
            f"consistency={summary.consistency_level}"
        )
    return results


def rescore_criteria(
    llm: DeepSeekClient,
    retriever: GraphRAGRetriever,
    section_name: str,
    student_text: str,
    previous_results: dict[str, CriterionSummary],
    criteria_to_rescore: list[str],
    feedback_map: dict[str, str],
    scoring_times: int = DEFAULT_SCORING_TIMES,
) -> dict[str, CriterionSummary]:
    context = retriever.retrieve_full_context(section_name)
    all_criteria = {c["criterion_name"]: c for c in context["criteria"]}

    updated_results = previous_results.copy()
    for crit_name in criteria_to_rescore:
        if crit_name not in all_criteria:
            raise ValueError(f"未找到指标：{crit_name}")
        crit_info = all_criteria[crit_name]
        feedback = feedback_map.get(
            crit_name,
            "审核未通过，请重新评分，注意证据真实性和量规一致性。",
        )
        print(f"  重评指标：{crit_name}，反馈：{feedback[:100]}...")
        new_summary = score_single_criterion(
            llm=llm,
            section_name=section_name,
            criterion_name=crit_name,
            weight=crit_info["weight"],
            rubrics=crit_info["rubrics"],
            exemplars=crit_info["exemplars"],
            student_text=student_text,
            scoring_times=scoring_times,
            audit_feedback=feedback,
        )
        updated_results[crit_name] = new_summary
        print(f"    重评完成：new_mean={new_summary.mean}")
    return updated_results
