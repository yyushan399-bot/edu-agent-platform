"""
批判性思维评分 Agent（从 preview-agent 迁移）。

对项目报告按 4 个二级指标（证据分析、数据分析、逻辑推演、局限性评价）进行
10 次独立采样评分，保留原有量规、片段抽取、RAG 对照与汇总逻辑。

对外统一接口：
    evaluate_critical(report_text: str) -> {"score": float, "feedback": str, "evidence": str}
"""

from __future__ import annotations

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
    "evidence_analysis": "证据分析",
    "data_analysis": "数据分析",
    "logical_reasoning": "逻辑推演",
    "limitation_evaluation": "局限性评价",
}

RUBRICS: Dict[str, str] = {
    "evidence_analysis": """
【证据分析】：
5分：对文献、理论进行系统考察。明确指出前人研究的局限性或矛盾点，并论述本研究如何弥补或改进。文献方面能辨析其权威性与条件异同。理论方面清晰交代核心公式或模型的原始假设条件，并专门论述这些假设在本研究情境中的满足程度或偏离影响。
4分：报告综合运用文献与理论证据，但分析深度略浅。文献以罗列为主，缺少主动的交叉对比或权重辨析。理论引用正确并解释了基本含义，能识别适用边界，但未专门论证其在本研究中的具体满足情况。
3分：证据类型较为单一或分析止于表层。文献仅被引用而无可靠性评述。理论仅提及名称或公式，未展开解释其内涵、假设或与研究的逻辑关联。
2分：证据来源贫乏且关联度弱。文献来源不可靠或与主题无关，理论引用错误或不适配当前情境，缺乏对理论前提的基本意识。
1分：无有效证据支撑。无效文献引用，或完全缺失理论依据内容。报告内容纯凭臆测或与探究无关的堆砌。
""",
    "data_analysis": """
【数据分析】：
5分：数据采集过程规范，包含重复测量、误差控制或质量检查。数据处理方法科学严谨，能够根据项目需要使用均值、标准差、误差分析、拟合、对比分析或其他适当方法。能够准确描述数据规律，并将处理结果与理论预期、模型预测或设计目标进行量化对照。
4分：数据采集较规范，记录较完整，处理方法基本正确。能够使用合适的统计或比较方法分析数据，并能将实验趋势与理论预期、模型预测或项目目标进行合理的定性或半定量对照。
3分：有基本的数据采集和处理过程，但数据记录、重复性、误差控制或分析方法不够充分。数据分析主要停留在简单计算、直接比较或表面趋势描述，缺少对数据结构和规律的深入提取。
2分：数据记录无序、不完整或处理方法存在明显错误。数据呈现较混乱，难以支持对项目结果的有效判断。
1分：没有进行有效的数据采集或数据分析，或所得数据、计算结果不具备科学意义，无法支撑项目结论。
""",
    "logical_reasoning": """
【逻辑推演】：
5分：推理链条清晰完整，关键前提交代充分，能够基于理论、数据或项目证据形成具体且可检验的判断。结论与证据之间具有较强一致性。能区分相关、因果、假设和推论，并能说明结论成立所依赖的条件或范围。
4分：能基于相关原理与数据对现象进行合理解释，结论方向与证据趋势基本一致。推理过程无明显漏洞，能够说明主要前提，但对复杂关系、条件限制或替代解释的分析稍显简略。
3分：能够根据数据或现象得出基本结论，但多为对表面趋势的直接概括。从原理到现象、从个别证据到一般判断的显性推理步骤不够充分，部分前提或条件说明不足。
2分：推理过程中存在较明显问题，如混淆相关与因果、以偏概全、循环论证，或使用不匹配的原理解释证据，导致结论可靠性较弱。
1分：未进行有效推理，或推理内容与项目主题、数据证据和研究问题基本无关。
""",
    "limitation_evaluation": """
【局限性评价】：
5分：能从数据质量、实验条件、变量控制、模型假设、样本范围、误差来源等方面，系统判断结论的可靠性和适用边界，并说明哪些结论可信、哪些需谨慎解释。
4分：能从数据质量、实验条件、变量控制、模型假设、样本范围、误差来源等方面能识别主要局限，并说明其对结论可靠性的影响。能基本判断结论的适用范围，但分析不够系统。
3分：能指出部分不足或误差来源，意识到结论有限制，但对其如何影响数据、推理或结论说明不够充分。
2分：局限性评价较表面，多为“有误差”、“不准确”等笼统表述，缺少与结论可靠性和适用范围的具体联系。
1分：没有有效评价局限性，或评价与项目实际不符，无法判断结论可信度。
""",
}

CRITICAL_KEYWORDS: Dict[str, List[str]] = {
    "证据分析": [
        "证据", "文献", "理论", "公式", "模型", "前人研究", "局限", "矛盾", "改进",
        "弥补", "权威性", "可靠性", "条件异同", "假设条件", "适用边界", "满足程度", "偏离影响",
    ],
    "数据分析": [
        "数据", "采集", "记录", "重复测量", "重复实验", "误差控制", "质量检查", "均值",
        "平均值", "标准差", "误差分析", "拟合", "对比分析", "趋势", "规律", "理论预期",
        "模型预测", "设计目标", "量化对照", "半定量",
    ],
    "逻辑推演": [
        "推理", "逻辑", "推演", "前提", "证据", "结论", "判断", "可检验", "一致性",
        "相关", "因果", "假设", "推论", "条件", "范围", "替代解释", "以偏概全", "循环论证",
    ],
    "局限性评价": [
        "局限", "局限性", "数据质量", "实验条件", "变量控制", "模型假设", "样本范围",
        "误差来源", "可靠性", "适用边界", "可信", "谨慎解释", "适用范围", "不足", "误差", "不准确",
    ],
}

EVIDENCE_MARKERS = [
    "如图", "表", "数据", "实验", "结果", "分析", "结论", "原因", "说明", "可见",
    "可以看出", "因此", "所以", "文献", "理论", "公式", "模型", "假设", "局限",
    "边界", "误差", "标准差", "拟合", "对比", "前提", "因果", "相关", "推论",
    "可靠性", "适用范围", "改进",
]

EVIDENCE_FALLBACK = "未能从报告中抽取到明确的批判性思维相关证据。"


class CriticalEvaluationResult(TypedDict):
    score: float
    feedback: str
    evidence: str


def _extract_keywords(dimension_name: str, rubric: str) -> List[str]:
    return extract_keywords_from_rubric(dimension_name, rubric, CRITICAL_KEYWORDS)


def score_student_chunk_relevance(
    chunk_text: str,
    dimension_name: str,
    rubric: str,
    keywords: List[str],
) -> int:
    score = 0
    chunk_text = chunk_text or ""

    if dimension_name in chunk_text:
        score += 8

    for kw in keywords:
        if kw in chunk_text:
            score += 3 if len(kw) >= 4 else 1

    for marker in EVIDENCE_MARKERS:
        if marker in chunk_text:
            score += 2

    return score


def _retrieve_student_dimension(
    report_context: str,
    dimension_name: str,
    rubric: str,
) -> tuple[str, Dict[str, Any]]:
    return retrieve_student_dimension_text(
        report_context,
        dimension_name,
        rubric,
        extract_keywords_fn=_extract_keywords,
        score_chunk_fn=score_student_chunk_relevance,
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


def to_unified_output(final_report: FinalGradeReport) -> CriticalEvaluationResult:
    return make_unified_output(final_report, evidence_fallback=EVIDENCE_FALLBACK)


def evaluate_critical(
    report_text: str,
    *,
    model: str = DEFAULT_MODEL,
    scoring_times: int = DEFAULT_SCORING_TIMES,
    rag_top_k: int = DEFAULT_RAG_TOP_K,
    api_key: Optional[str] = None,
) -> CriticalEvaluationResult:
    """
    对批判性思维四个二级指标进行评分，返回统一 JSON 结构。

    Returns:
        {"score": float, "feedback": str, "evidence": str}
        score 为四维度均分（1.0–5.0）。
    """
    return evaluate_report(
        report_text,
        scoring_dimensions=SCORING_DIMENSIONS,
        rubrics=RUBRICS,
        model=model,
        empty_message="报告文本为空，无法进行批判性思维评分。",
        failure_message="批判性思维评分失败。",
        evidence_fallback=EVIDENCE_FALLBACK,
        retrieve_student_fn=_retrieve_student_dimension,
        build_prompt_fn=build_physics_pbl_scoring_prompt,
        scoring_times=scoring_times,
        rag_top_k=rag_top_k,
        api_key=api_key,
    )


evaluate = evaluate_critical


def run_grading_from_text(
    report_text: str,
    *,
    model: str = DEFAULT_MODEL,
    scoring_times: int = DEFAULT_SCORING_TIMES,
    rag_top_k: int = DEFAULT_RAG_TOP_K,
) -> Dict[str, Any]:
    """兼容 preview-agent 风格的完整结果。对外推荐使用 evaluate_critical()。"""
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
    "CriticalEvaluationResult",
    "DeepSeekClient",
    "DimensionScoreSummary",
    "FinalGradeReport",
    "RUBRICS",
    "SCORING_DIMENSIONS",
    "aggregate_final_report",
    "evaluate",
    "evaluate_critical",
    "run_grading_from_text",
    "score_one_dimension",
    "to_unified_output",
]
