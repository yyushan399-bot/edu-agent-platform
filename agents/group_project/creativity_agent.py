"""
创造性思维评分 Agent（从 preview-agent 迁移）。

对项目报告按 4 个二级指标（问题提出、方案新颖性、创新表征、创新表达）进行
10 次独立采样评分，保留原有量规、片段抽取、RAG 对照与汇总逻辑。

对外统一接口：
    evaluate_creativity(report_text: str) -> {"score": float, "feedback": str, "evidence": str}
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
from agents.group_project.scoring_prompt_utils import build_creativity_scoring_prompt  # noqa: E402
from agents.group_project.scoring_report import aggregate_final_report, make_unified_output  # noqa: E402
from agents.group_project.scoring_utils import (  # noqa: E402
    extract_keywords_from_rubric,
    retrieve_student_dimension_text,
)

SCORING_DIMENSIONS = {
    "problem_posing": "问题提出",
    "plan_novelty": "方案新颖性",
    "innovation_representation": "创新表征",
    "innovation_expression": "创新表达",
}

RUBRICS: Dict[str, str] = {
    "problem_posing": """
【问题提出】：
5分：能从非显而易见的理论视角或跨学科维度切入，提出具有独特性的问题结构。能打破常规思维定式，展现出对问题内涵的重新框定与深度挖掘，问题具备向新情境迁移的生成潜力。
4分：能选择较为新颖的切入角度，问题结构具有一定独特性，能体现对常规思路的主动突破，而非对常见主题的直接平移。
3分：能提出基本明确的问题，但切入角度较为常规，问题结构缺乏明显的自主重构痕迹。
2分：问题多为对常规主题或常见任务的直接搬用，缺少自主加工和视角选择，问题与常规做法无明显差异。
1分：没有明确项目问题，或问题与项目主题脱节，缺少探究价值。


评分提醒：本维度只评价“问题如何被提出和重新框定”，不要把后续实验步骤、工具使用或成果表达当作主要加分依据。
""",
    "plan_novelty": """
【方案新颖性】：
5分：方案在方法、装置、模型、技术路线或实现方式等关键环节有明确自主创新，并能清楚说明其相较常规方案的独特之处和创新依据。
4分：方案在器材、流程、结构、模型或技术路线等方面有一定自主改进，能说明主要新意，但创新深度或独特性阐释不够充分，或未涉及关键环节。
3分：方案主要借鉴已有案例或教师建议，有少量调整、组合或替换，但自主创新较少，且多体现在局部或非关键环节。
2分：方案基本沿用已有做法，缺少明显自主设计。即使有修改，也未说明其新意或创新依据。
1分：难以识别自主创新，或方案拼凑、照搬明显，无法体现方案新颖性。


评分提醒：本维度只评价“方案本身的新颖性与自主改进”，不要用实验方案完整性、变量控制严谨性替代创新性评分。
""",
    "innovation_representation": """
【创新表征】：
5分：文中明确提及使用了专业工具（如MATLAB, Origin, Python, Seaborn, CAD等进行复杂可视化建模。能自主选择或设计合适的模型、图示、草图、流程图、数据图表等表征方式，清楚呈现问题结构、方案机制或成果特点。能对图表或模型中的关键要素、关系和变化进行解释，并说明其对创新设计或优化的作用。
4分：有目的地选用合适工具辅助表达。能较恰当地使用模型、图示或图表表达项目思路和关键关系。能对主要信息作出解释，并基本说明其与方案、结果或改进的联系，但创新作用阐释不够充分。
3分：技术工具使用较为基础（仅简单记录）。能使用基本表征方式展示项目内容，并作简单说明，但多停留在现象描述或内容罗列，对结构关系、机制原理或创新价值解释不足。
2分：软件使用被动或不当。表征较粗糙，存在要素缺失、标注不清或关系不准等问题。对图表或模型缺少有效解释，难以支撑项目说明。
1分：缺少有效表征，或表征与项目内容无关。没有对图表、模型或数据内容进行有效解释。


评分提醒：本维度强调“表征方式如何支撑创新”，不仅看是否有图表或软件名，还要看是否解释了关键关系、机制和优化作用。
""",
    "innovation_expression": """
【创新表达】：
5分：能清晰指出核心创新点，说明其相较常规做法或已有方案的改进，并结合情境阐释应用价值、适用条件、迁移可能和局限。
4分：能明确说明主要创新点及其对解决问题、优化方案或提升效果的作用，并能说明一定的应用意义，但对适用范围或局限阐释不够充分。
3分：能基本说明创新点，但多为罗列，核心贡献不突出。对成果意义、应用场景或改进价值说明较笼统。
2分：创新点说明模糊，难以看出与常规做法的区别。成果价值阐释空泛，与实际问题或应用情境联系较弱。
1分：未能识别或说明创新点，或创新与项目内容无关。缺少对成果价值、应用意义或可迁移性的说明。


评分提醒：本维度只评价“创新点与价值是否被说清楚”，重点关注常规对比、应用情境、适用条件、迁移可能和局限。
""",
}

CREATIVITY_KEYWORDS: Dict[str, List[str]] = {
    "问题提出": [
        "研究问题", "问题提出", "提出问题", "研究背景", "问题来源",
        "切入角度", "跨学科", "问题重构", "探究价值", "研究目的",
    ],
    "方案新颖性": [
        "方案新颖性", "新颖性", "自主创新", "自主设计", "创新方案",
        "改进结构", "改进方法", "改进装置", "技术路线创新",
        "不同于", "相比传统", "独特之处", "创新依据",
    ],
    "创新表征": [
        "创新表征", "表征", "可视化", "图表", "流程图", "示意图",
        "模型图", "结构图", "数据图", "曲线", "Tracker", "Python",
        "Scipy", "MATLAB", "Origin", "CAD", "模型",
    ],
    "创新表达": [
        "创新表达", "创新点", "核心创新点", "核心创新", "应用价值",
        "适用条件", "迁移可能", "推广", "局限", "成果价值",
    ],
}

EVIDENCE_MARKERS = [
    "如图", "表", "数据", "实验", "方案", "结果", "分析", "结论",
    "原因", "说明", "可见", "可以看出", "因此", "所以",
    "变量", "控制变量", "误差", "改进", "器材", "步骤",
    "理论", "公式", "模型", "建模", "问题", "创新", "创新点",
    "可视化", "图表", "趋势", "异常", "应用", "迁移",
]

EVIDENCE_FALLBACK = "未能从报告中抽取到明确的创造性思维相关证据。"


class CreativityEvaluationResult(TypedDict):
    score: float
    feedback: str
    evidence: str


def _extract_keywords(dimension_name: str, rubric: str) -> List[str]:
    return extract_keywords_from_rubric(dimension_name, rubric, CREATIVITY_KEYWORDS)


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
        build_prompt_fn=build_creativity_scoring_prompt,
    )


def to_unified_output(final_report: FinalGradeReport) -> CreativityEvaluationResult:
    return make_unified_output(final_report, evidence_fallback=EVIDENCE_FALLBACK)


def evaluate_creativity(
    report_text: str,
    *,
    model: str = DEFAULT_MODEL,
    scoring_times: int = DEFAULT_SCORING_TIMES,
    rag_top_k: int = DEFAULT_RAG_TOP_K,
    api_key: Optional[str] = None,
) -> CreativityEvaluationResult:
    """
    对创造性思维四个二级指标进行评分，返回统一 JSON 结构。

    Args:
        report_text: 学生项目报告纯文本。
        model: LLM 模型名称。
        scoring_times: 每个维度独立评分次数，默认 10。
        rag_top_k: 每维 RAG 检索片段数，默认 8。
        api_key: 可选，覆盖环境变量中的 API Key。

    Returns:
        {"score": float, "feedback": str, "evidence": str}
        score 为四维度均分（1.0–5.0，保留原有 1–5 分量规尺度）。
    """
    return evaluate_report(
        report_text,
        scoring_dimensions=SCORING_DIMENSIONS,
        rubrics=RUBRICS,
        model=model,
        empty_message="报告文本为空，无法进行创造性思维评分。",
        failure_message="创造性思维评分失败。",
        evidence_fallback=EVIDENCE_FALLBACK,
        retrieve_student_fn=_retrieve_student_dimension,
        build_prompt_fn=build_creativity_scoring_prompt,
        scoring_times=scoring_times,
        rag_top_k=rag_top_k,
        api_key=api_key,
    )


evaluate = evaluate_creativity


def run_grading_from_text(
    report_text: str,
    *,
    model: str = DEFAULT_MODEL,
    scoring_times: int = DEFAULT_SCORING_TIMES,
    rag_top_k: int = DEFAULT_RAG_TOP_K,
) -> Dict[str, Any]:
    """
    兼容 preview-agent 风格的完整结果（含 dimension_results / final_report）。
    对外推荐使用 evaluate_creativity()。
    """
    return _run_grading_from_text(
        report_text,
        scoring_dimensions=SCORING_DIMENSIONS,
        rubrics=RUBRICS,
        model=model,
        evidence_fallback=EVIDENCE_FALLBACK,
        retrieve_student_fn=_retrieve_student_dimension,
        build_prompt_fn=build_creativity_scoring_prompt,
        scoring_times=scoring_times,
        rag_top_k=rag_top_k,
    )


__all__ = [
    "CreativityEvaluationResult",
    "DeepSeekClient",
    "DimensionScoreSummary",
    "FinalGradeReport",
    "RUBRICS",
    "SCORING_DIMENSIONS",
    "aggregate_final_report",
    "evaluate",
    "evaluate_creativity",
    "run_grading_from_text",
    "score_one_dimension",
    "to_unified_output",
]
