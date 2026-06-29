"""
问题解决能力评分 Agent（从 preview-agent 迁移）。

对项目报告按 4 个二级指标（问题界定、方案建构、方案实施、反思调节）进行
10 次独立采样评分，保留原有量规、片段抽取、RAG 对照与汇总逻辑。

对外统一接口：
    evaluate_problemsolving(report_text: str) -> {"score": float, "feedback": str, "evidence": str}
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from dotenv import load_dotenv

_AGENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _AGENT_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
load_dotenv(_PROJECT_ROOT / ".env")

from agents.group_project.pbl_config import (  # noqa: E402
    DEEPSEEK_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_RAG_TOP_K,
    DEFAULT_SCORING_TIMES,
)
from agents.group_project.scoring_engine import (  # noqa: E402
    evaluate_report,
    run_grading_from_text as _run_grading_from_text,
    score_one_dimension as _score_one_dimension,
)
from agents.group_project.scoring_models import (  # noqa: E402
    DeepSeekClient,
    DimensionScoreSummary,
    FinalGradeReport,
)
from agents.group_project.scoring_prompt_utils import build_physics_pbl_scoring_prompt  # noqa: E402
from agents.group_project.scoring_report import aggregate_final_report, make_unified_output  # noqa: E402
from agents.group_project.scoring_utils import (  # noqa: E402
    extract_keywords_from_rubric,
    retrieve_student_dimension_text,
)

SCORING_DIMENSIONS = {
    "problem_definition": "问题界定",
    "solution_construction": "方案建构",
    "solution_implementation": "方案实施",
    "reflection_adjustment": "反思调节",
}

RUBRICS: Dict[str, str] = {
    "problem_definition": """
【问题界定】：
5分：明确定义自变量、因变量与控制变量，且包含具体的量纲、数值范围或物理约束声明。假设表述包含可量化的检验指标。清晰划定系统的边界条件与适用限制。
4分：定义了关键变量与主要约束，但缺少具体的量纲或数值区间。假设具备方向性，量化和操作性基本清晰，但检验路径的描述有少量操作细节留白。
3分：变量界定笼统。假设宽泛，缺乏可测量指标。未设立专门的问题定义或假设段落，信息散落在步骤中。
2分：出现变量混用，导致研究边界不清。提出的假设属于模糊的猜测，不具备检验性。
1分：论述内容与主题严重脱节，完全无变量界定。无假设或假设完全不具备科学/工程意义。

评分提醒：本维度只评价“研究问题如何被界定（变量、假设、边界）”，不要把后续实验步骤完整性、方案新颖性或结果分析当作主要加分依据。
""",
    "solution_construction": """
【方案建构】：
5分：方案结构完整，包含明确的实验或项目目标、理论依据、操作步骤、变量控制、数据记录计划和误差控制预案。方案具有较高可行性和可重复性，能够有效回应研究问题。
4分：方案步骤清晰，结构较合理，变量控制和数据记录安排基本充分。整体可行，但对误差控制、实施条件或操作细节说明略有不足。
3分：方案具备基本框架，但部分步骤描述不够具体。变量控制不够严格，实施中可能存在一定操作困难。
2分：方案结构松散，缺少关键步骤或变量控制说明。存在明显可行性问题，如变量混淆、器材条件不匹配或操作流程不完整。
1分：缺少有效方案，或方案完全不可操作。设计违背基本科学或工程原理。

评分提醒：本维度只评价“方案设计是否完整、可行、可重复”，不要用实施过程记录是否详细、或结果好坏替代方案建构评分。
""",
    "solution_implementation": """
【方案实施】：
5分：过程记录完整清楚，能够呈现实验、建模、设计、制作、测试或验证的关键步骤与关键条件。实施过程与研究问题、方案设计、变量控制或设计约束保持一致。结果能够明确回应研究问题或项目目标，并能对应预设评价指标。
4分：过程记录较完整，能够呈现主要实施步骤和关键结果。记录内容与研究问题和方案设计基本一致，结果能够较好回应研究问题或项目目标，但对部分条件、现象或评价指标说明不够充分。
3分：有基本过程记录，但关键步骤、条件、现象或测试结果描述不够充分。结果与研究问题有一定关联，但对目标达成程度的说明不够清楚。
2分：过程记录零散或缺失较多，难以看出方案如何实施。结果与研究问题或项目目标联系较弱，无法充分判断方案是否有效。
1分：缺少过程记录，或结果无法回应研究问题、项目目标和方案设计。

评分提醒：本维度只评价“方案是否被如实实施、过程与结果是否回应研究问题”，不要用方案设计完整性或反思改进质量替代实施评分。
""",
    "reflection_adjustment": """
【反思调节】：
5分：能基于实施过程、结果和问题等提出具体、可操作、有针对性的改进方案。能说明改什么、怎么改，以及预期改进效果。
4分：能针对主要问题提出较合理的改进方向，具有一定可行性。能说明改进环节和可能效果，但实施细节不够充分。
3分：能提出一般性改进建议，如增加实验次数、改进装置或优化流程等，但较笼统，缺少具体操作办法。
2分：反思较表面，改进建议空泛或可行性较弱，与实际问题联系不清。
1分：没有提出实质性改进方案，或改进建议与项目问题无关。

评分提醒：本维度只评价“反思与改进是否具体可操作”，不要用问题界定清晰度或方案/实施质量替代反思调节评分。
""",
}

PROBLEMSOLVING_DIMENSION_STRONG_KEYWORDS: Dict[str, List[str]] = {
    "问题界定": [
        "研究问题", "问题界定", "问题定义", "自变量", "因变量", "控制变量",
        "变量界定", "核心假设", "研究假设", "假设", "量纲", "单位",
        "数值范围", "物理约束", "边界条件", "适用限制", "检验指标",
        "可量化", "可测量", "可检验",
    ],
    "方案建构": [
        "方案建构", "方案设计", "实验方案", "项目目标", "实验目标",
        "理论依据", "操作步骤", "实施步骤", "实验步骤", "流程",
        "技术路线", "变量控制", "数据记录计划", "误差控制预案",
        "可行性", "可重复性", "器材条件",
    ],
    "方案实施": [
        "方案实施", "实施过程", "实验过程", "建模过程", "制作过程",
        "测试过程", "验证过程", "过程记录", "实验记录", "关键步骤",
        "关键条件", "测试结果", "验证结果", "结果回应", "评价指标",
        "目标达成",
    ],
    "反思调节": [
        "反思调节", "反思", "问题反思", "总结反思", "改进", "改进方案",
        "优化", "优化方案", "调整", "存在问题", "主要问题", "不足",
        "改进方向",
    ],
}

EXCLUDE_HINTS: Dict[str, List[str]] = {
    "问题界定": [
        "实验过程", "实验分析", "研究结论", "改进建议", "图片文件",
    ],
    "方案建构": [
        "研究结论", "误差分析", "反思", "改进建议",
    ],
    "方案实施": [
        "研究背景", "问题提出", "理论依据", "方案设计思路", "改进建议",
    ],
    "反思调节": [
        "自变量", "因变量", "实验步骤", "理论模型", "研究背景",
    ],
}

EVIDENCE_FALLBACK = "未能从报告中抽取到明确的问题解决相关证据。"


class ProblemSolvingEvaluationResult(TypedDict):
    score: float
    feedback: str
    evidence: str


def clean_report_context_for_student_chunks(report_context: str) -> str:
    """清理系统拼接标题，避免 student_dimension_text 的原文中出现系统标签。"""
    text = report_context or ""
    remove_markers = [
        "# 当前学生报告正文",
        "# 当前学生报告中的图片 / 图表 / 截图解析内容",
        "[未检测到图片，或图片未被提取。]",
    ]
    for marker in remove_markers:
        text = text.replace(marker, "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_keywords(dimension_name: str, rubric: str) -> List[str]:
    return extract_keywords_from_rubric(
        dimension_name,
        rubric,
        PROBLEMSOLVING_DIMENSION_STRONG_KEYWORDS,
    )


def score_student_chunk_relevance(
    chunk_text: str,
    dimension_name: str,
    rubric: str,
    keywords: List[str],
) -> int:
    score = 0
    chunk_text = chunk_text or ""

    strong_keywords = PROBLEMSOLVING_DIMENSION_STRONG_KEYWORDS.get(dimension_name, [])
    exclude_hints = EXCLUDE_HINTS.get(dimension_name, [])

    if dimension_name in chunk_text:
        score += 12

    for kw in strong_keywords:
        if kw and kw in chunk_text:
            score += 8

    for kw in keywords:
        if kw and kw in chunk_text:
            if len(kw) >= 5:
                score += 2
            elif len(kw) >= 3:
                score += 1

    for hint in exclude_hints:
        if hint and hint in chunk_text:
            score -= 3

    if dimension_name == "问题界定":
        if any(x in chunk_text for x in ["自变量", "因变量", "控制变量", "研究假设", "边界条件", "检验指标"]):
            score += 10
        else:
            score -= 4

    if dimension_name == "方案建构":
        if any(x in chunk_text for x in ["实验方案", "操作步骤", "变量控制", "数据记录", "误差控制", "可行性"]):
            score += 10
        else:
            score -= 4

    if dimension_name == "方案实施":
        if any(x in chunk_text for x in ["实验过程", "实施过程", "测试结果", "验证结果", "过程记录", "制作"]):
            score += 10
        else:
            score -= 4

    if dimension_name == "反思调节":
        if any(x in chunk_text for x in ["反思", "改进", "优化", "不足", "局限", "预期效果"]):
            score += 10
        else:
            score -= 6

    return max(score, 0)


def _retrieve_student_dimension(
    report_context: str,
    dimension_name: str,
    rubric: str,
) -> tuple[str, Dict[str, Any]]:
    return retrieve_student_dimension_text(
        report_context,
        dimension_name,
        rubric,
        max_chunk_chars=450,
        extract_keywords_fn=_extract_keywords,
        score_chunk_fn=score_student_chunk_relevance,
        preprocess_context_fn=clean_report_context_for_student_chunks,
    )


def score_one_dimension(
    llm: DeepSeekClient,
    dimension_key: str,
    dimension_name: str,
    rubric: str,
    merged_report_context: str,
    scoring_times: int = DEFAULT_SCORING_TIMES,
    rag_top_k: int = DEFAULT_RAG_TOP_K,
    audit_feedback: Optional[Dict[str, Any]] = None,
) -> DimensionScoreSummary:
    return _score_one_dimension(
        llm=llm,
        dimension_key=dimension_key,
        dimension_name=dimension_name,
        rubric=rubric,
        merged_report_context=merged_report_context,
        scoring_times=scoring_times,
        rag_top_k=rag_top_k,
        audit_feedback=audit_feedback,
        retrieve_student_fn=_retrieve_student_dimension,
        build_prompt_fn=build_physics_pbl_scoring_prompt,
    )


def to_unified_output(final_report: FinalGradeReport) -> ProblemSolvingEvaluationResult:
    return make_unified_output(final_report, evidence_fallback=EVIDENCE_FALLBACK)


def evaluate_problemsolving(
    report_text: str,
    *,
    model: str = DEFAULT_MODEL,
    scoring_times: int = DEFAULT_SCORING_TIMES,
    rag_top_k: int = DEFAULT_RAG_TOP_K,
    api_key: Optional[str] = None,
) -> ProblemSolvingEvaluationResult:
    """
    对问题解决能力四个二级指标进行评分，返回统一 JSON 结构。

    Returns:
        {"score": float, "feedback": str, "evidence": str}
        score 为四维度均分（1.0–5.0）。
    """
    return evaluate_report(
        report_text,
        scoring_dimensions=SCORING_DIMENSIONS,
        rubrics=RUBRICS,
        model=model,
        empty_message="报告文本为空，无法进行问题解决能力评分。",
        failure_message="问题解决能力评分失败。",
        evidence_fallback=EVIDENCE_FALLBACK,
        retrieve_student_fn=_retrieve_student_dimension,
        build_prompt_fn=build_physics_pbl_scoring_prompt,
        scoring_times=scoring_times,
        rag_top_k=rag_top_k,
        api_key=api_key,
    )


evaluate = evaluate_problemsolving


def run_grading_from_text(
    report_text: str,
    *,
    model: str = DEFAULT_MODEL,
    scoring_times: int = DEFAULT_SCORING_TIMES,
    rag_top_k: int = DEFAULT_RAG_TOP_K,
) -> Dict[str, Any]:
    """兼容 preview-agent 风格的完整结果。对外推荐使用 evaluate_problemsolving()。"""
    return _run_grading_from_text(
        report_text,
        scoring_dimensions=SCORING_DIMENSIONS,
        rubrics=RUBRICS,
        model=model,
        evidence_fallback=EVIDENCE_FALLBACK,
        retrieve_student_fn=_retrieve_student_dimension,
        build_prompt_fn=build_physics_pbl_scoring_prompt,
        scoring_times=scoring_times,
        rag_top_k=rag_top_k,
    )


__all__ = [
    "ProblemSolvingEvaluationResult",
    "DeepSeekClient",
    "DimensionScoreSummary",
    "FinalGradeReport",
    "RUBRICS",
    "SCORING_DIMENSIONS",
    "aggregate_final_report",
    "evaluate",
    "evaluate_problemsolving",
    "run_grading_from_text",
    "score_one_dimension",
    "to_unified_output",
]
