"""
创造性思维评分 Agent（从 preview-agent 迁移）。

对项目报告按 4 个二级指标（问题提出、方案新颖性、创新表征、创新表达）进行
10 次独立采样评分，保留原有量规、片段抽取、RAG 对照与汇总逻辑。

对外统一接口：
    evaluate_creativity(report_text: str) -> {"score": float, "feedback": str, "evidence": str}
"""

from __future__ import annotations

import json
import os
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

_AGENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _AGENT_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
load_dotenv(_PROJECT_ROOT / ".env")

try:
    from services.rag_service import retrieve_rag_context_auto
except Exception:
    retrieve_rag_context_auto = None


# ============================================================
# 基础配置
# ============================================================

DEEPSEEK_BASE_URL = os.getenv("OPENAI_BASE_URL", os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"))

DEFAULT_SCORING_TIMES = 10
DEFAULT_RAG_TOP_K = 8

SCORING_DIMENSIONS = {
    "problem_posing": "问题提出",
    "plan_novelty": "方案新颖性",
    "innovation_representation": "创新表征",
    "innovation_expression": "创新表达",
}

RAG_INDICATOR_FILTERS = {
    "problem_posing": {
        "dimension": "创造性思维",
        "indicator": "问题提出",
        "indicator_key": "problem_posing",
    },
    "plan_novelty": {
        "dimension": "创造性思维",
        "indicator": "方案新颖性",
        "indicator_key": "plan_novelty",
    },
    "innovation_representation": {
        "dimension": "创造性思维",
        "indicator": "创新表征",
        "indicator_key": "innovation_representation",
    },
    "innovation_expression": {
        "dimension": "创造性思维",
        "indicator": "创新表达",
        "indicator_key": "innovation_expression",
    },
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


# ============================================================
# 数据结构
# ============================================================

class SingleScore(BaseModel):
    score: int = Field(..., ge=1, le=5)
    reason: str
    evidence: List[str] = Field(default_factory=list)
    reference_comparison: str = ""
    weakness: str = ""
    suggestion: str = ""


class DimensionScoreSummary(BaseModel):
    dimension_key: str
    dimension_name: str
    student_dimension_text: str = ""
    student_dimension_debug: Dict[str, Any] = Field(default_factory=dict)
    scores: List[SingleScore]
    mean: float
    std: float
    cv: Optional[float]
    min_score: float
    max_score: float
    consistency_level: str
    summary_comment: str


class FinalGradeReport(BaseModel):
    dimension_summary: List[Dict[str, Any]]
    dimension_summary_text: str
    dimension_results: Dict[str, DimensionScoreSummary]
    strengths: List[str]
    weaknesses: List[str]
    revision_suggestions: List[str]
    risk_flags: List[str]
    final_comment: str


class WorkflowState(TypedDict, total=False):
    report_text: str
    merged_report_context: str
    dimension_results: Dict[str, Dict[str, Any]]
    final_report: Dict[str, Any]
    errors: List[str]


class CreativityEvaluationResult(TypedDict):
    score: float
    feedback: str
    evidence: str


# ============================================================
# LLM 客户端
# ============================================================

class DeepSeekClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        base_url: str = DEEPSEEK_BASE_URL,
        temperature: float = 0.0,
        top_p: float = 0.9,
        max_tokens: int = 4000,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError(
                "缺少 API Key。请在项目根目录 .env 中设置 OPENAI_API_KEY 或 DEEPSEEK_API_KEY。"
            )

        normalized_base = base_url.rstrip("/")
        if "deepseek.com" in normalized_base and not normalized_base.endswith("/v1"):
            normalized_base = f"{normalized_base}/v1"

        self.client = OpenAI(api_key=self.api_key, base_url=normalized_base)
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        retry: int = 3,
    ) -> Dict[str, Any]:
        last_error: Optional[Exception] = None

        for attempt in range(1, retry + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=self.temperature if temperature is None else temperature,
                    top_p=self.top_p,
                    max_tokens=self.max_tokens,
                    stream=False,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("模型返回为空。")
                return safe_json_loads(content)
            except Exception as exc:
                last_error = exc
                time.sleep(1.2 * attempt)

        raise RuntimeError(f"LLM API 调用失败，最后错误：{last_error}")

    def chat_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        retry: int = 3,
    ) -> str:
        last_error: Optional[Exception] = None

        for attempt in range(1, retry + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=self.temperature if temperature is None else temperature,
                    top_p=self.top_p,
                    max_tokens=self.max_tokens,
                    stream=False,
                )
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("模型返回为空。")
                return content
            except Exception as exc:
                last_error = exc
                time.sleep(1.2 * attempt)

        raise RuntimeError(f"LLM API 调用失败，最后错误：{last_error}")


# ============================================================
# 工具函数（含 scoring_prompt_utils 内联）
# ============================================================

def format_student_report_sections(
    *,
    dimension_name: str,
    student_dimension_text: str,
) -> str:
    """评分 prompt 共用：只使用学生报告「本维度相关片段」。"""
    primary = (student_dimension_text or "").strip()
    if not primary:
        primary = (
            "[未能从学生报告中抽取到与当前维度明显相关的片段。"
            f"请仅基于这一缺失情况评价【{dimension_name}】维度，"
            "不得查阅或引用完整报告其他内容。]"
        )

    return f"""
# 当前学生报告相关片段（【{dimension_name}】维度，唯一学生依据）

以下片段由系统从学生报告中按当前维度与量规自动抽取，是评分时唯一可使用的学生报告依据。
- evidence 必须来自这些片段中的原文短句
- 不得使用完整报告其他部分作为补充依据
- 如果片段中没有体现某项能力，应按“未体现/证据不足”处理，不得从全文其他位置补足

{primary}
""".strip()


def safe_json_loads(text: str) -> Dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"无法解析 JSON：{text[:500]}")


def truncate_text(text: str, max_chars: int = 120_000) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[系统提示：原报告内容过长，已截断。]"


def ensure_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value]
    return [str(value)]


def build_merged_report_context(report_text: str) -> str:
    report_text = (report_text or "").strip()
    merged = "# 当前学生报告正文\n" + (report_text if report_text else "[无可提取正文]")
    return truncate_text(merged)


def split_report_into_chunks(
    report_context: str,
    max_chunk_chars: int = 800,
    overlap_chars: int = 120,
) -> List[Dict[str, Any]]:
    report_context = report_context or ""
    chunks: List[Dict[str, Any]] = []
    if not report_context.strip():
        return chunks

    start = 0
    chunk_index = 1
    text_length = len(report_context)

    while start < text_length:
        end = min(start + max_chunk_chars, text_length)
        chunk_text = report_context[start:end].strip()
        if chunk_text:
            chunks.append(
                {
                    "chunk_id": f"student_chunk_{chunk_index}",
                    "text": chunk_text,
                    "start": start,
                    "end": end,
                }
            )
            chunk_index += 1
        if end >= text_length:
            break
        start = max(0, end - overlap_chars)

    return chunks


def extract_keywords_for_dimension(dimension_name: str, rubric: str) -> List[str]:
    base_keywords = {
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

    keywords = list(base_keywords.get(dimension_name, []))
    rubric_text = rubric or ""
    candidate_terms = re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", rubric_text)
    stop_terms = {
        "评分", "量规", "报告", "学生", "当前", "维度", "进行",
        "能够", "没有", "缺少", "清晰", "明确", "具体",
        "基本", "严重", "完全", "相关", "内容", "情况",
        "之间", "部分", "分析", "评价",
    }
    for term in candidate_terms:
        if term not in stop_terms and term not in keywords:
            keywords.append(term)
    return keywords[:80]


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

    evidence_markers = [
        "如图", "表", "数据", "实验", "方案", "结果", "分析", "结论",
        "原因", "说明", "可见", "可以看出", "因此", "所以",
        "变量", "控制变量", "误差", "改进", "器材", "步骤",
        "理论", "公式", "模型", "建模", "问题", "创新", "创新点",
        "可视化", "图表", "趋势", "异常", "应用", "迁移",
    ]
    for marker in evidence_markers:
        if marker in chunk_text:
            score += 2

    return score


def retrieve_student_dimension_text(
    report_context: str,
    dimension_name: str,
    rubric: str,
    top_k: int = 5,
    max_chunk_chars: int = 800,
) -> tuple[str, Dict[str, Any]]:
    chunks = split_report_into_chunks(
        report_context=report_context,
        max_chunk_chars=max_chunk_chars,
        overlap_chars=120,
    )
    keywords = extract_keywords_for_dimension(dimension_name=dimension_name, rubric=rubric)

    scored_chunks: List[Dict[str, Any]] = []
    for chunk in chunks:
        score = score_student_chunk_relevance(
            chunk_text=chunk["text"],
            dimension_name=dimension_name,
            rubric=rubric,
            keywords=keywords,
        )
        scored_chunks.append({**chunk, "score": score})

    scored_chunks.sort(key=lambda x: x["score"], reverse=True)
    selected_chunks = [item for item in scored_chunks if item["score"] > 0][:top_k]
    if not selected_chunks:
        selected_chunks = scored_chunks[: min(top_k, len(scored_chunks))]

    blocks = []
    for i, item in enumerate(selected_chunks, start=1):
        blocks.append(
            f"""
【学生报告{dimension_name}相关片段 {i}】
片段ID：{item["chunk_id"]}
相关性分数：{item["score"]}
原文：
{item["text"]}
""".strip()
        )

    student_dimension_text = "\n\n".join(blocks)
    debug = {
        "dimension_name": dimension_name,
        "top_k": top_k,
        "chunk_count": len(chunks),
        "selected_count": len(selected_chunks),
        "keywords": keywords,
        "selected_chunks": selected_chunks,
    }
    return student_dimension_text, debug


def retrieve_reference_context_for_dimension(
    report_context: str,
    dimension_key: str,
    dimension_name: str,
    rubric: str,
    top_k: int = DEFAULT_RAG_TOP_K,
) -> tuple[str, Dict[str, Any]]:
    if retrieve_rag_context_auto is None:
        return (
            "[RAG 未启用：无法加载 services.rag_service。]",
            {
                "enabled": False,
                "error": "无法导入 services.rag_service.retrieve_rag_context_auto",
                "dimension_key": dimension_key,
                "dimension_name": dimension_name,
                "top_k": top_k,
            },
        )

    try:
        rag_context, rag_debug = retrieve_rag_context_auto(
            report_context=report_context,
            dimension_name=dimension_name,
            rubric=rubric,
            top_k=top_k,
        )
        if not isinstance(rag_debug, dict):
            rag_debug = {"raw_debug": rag_debug}
        rag_debug.setdefault("enabled", True)
        rag_debug.setdefault("dimension_key", dimension_key)
        rag_debug.setdefault("dimension_name", dimension_name)
        rag_debug.setdefault("top_k", top_k)
        return rag_context, rag_debug
    except Exception as exc:
        return (
            f"[RAG 检索失败：{exc}]",
            {
                "enabled": False,
                "error": str(exc),
                "dimension_key": dimension_key,
                "dimension_name": dimension_name,
                "top_k": top_k,
            },
        )


def format_audit_feedback_for_prompt(audit_feedback: Optional[Dict[str, Any]]) -> str:
    if not audit_feedback:
        return "[首次评分，或本维度没有上一轮审核反馈。]"
    try:
        return json.dumps(audit_feedback, ensure_ascii=False, indent=2)[:8000]
    except Exception:
        return str(audit_feedback)[:8000]


def build_dimension_scoring_prompt(
    dimension_key: str,
    dimension_name: str,
    rubric: str,
    merged_report_context: str,
    student_dimension_text: str,
    rag_context: str,
    round_index: int,
    audit_feedback: Optional[Dict[str, Any]] = None,
) -> tuple[str, str]:
    audit_feedback_text = format_audit_feedback_for_prompt(audit_feedback)
    primary_block = format_student_report_sections(
        dimension_name=dimension_name,
        student_dimension_text=student_dimension_text,
    )

    system_prompt = f"""
作为一名资深项目化学习与创造性思维评价专家，你的职责是根据创造性思维评价量规，对学生项目报告评分。你需要根据项目报告【{dimension_name}】维度的情况，对学生的项目报告给出1到5之间的分数。

你必须遵守：
1. 只评价当前维度：{dimension_name}
2. 评分范围为1-5分整数
3. 必须基于当前学生报告（「当前维度相关片段」）进行判断
4. 评分依据只能是「当前学生报告相关片段」；
5. RAG 参考片段只作为评分标尺和对照样例，不能把参考报告内容当作当前学生报告内容
6. student_dimension_text 必须来自当前学生报告，不能来自 RAG 参考报告
7. 不要编造当前学生报告中不存在的内容
8. 如果当前学生报告没有体现某项能力，应明确指出缺失，而不是根据参考片段补充
9. 输出必须是 JSON object，不要输出 Markdown
10. 本次是第 {round_index} 次独立评分，请独立判断，不要假设其他评分结果
11. 如果提供了“上一轮审核不通过原因”，你必须在本次评分时重点修正这些问题
12. 不要机械迎合审核意见，最终仍必须基于学生报告相关片段/补充全文与当前维度量规进行独立评分
13. 如果上一轮问题是证据不可追溯，本次 evidence 必须是引用「当前维度相关片段」中的原文短句，不能引用 RAG 参考片段
14. 如果上一轮问题是量规不匹配，本次必须严格对齐【{dimension_name}】维度量规，不要混入其他维度标准
15. 如果上一轮问题是分数—理由不一致，本次必须保证 score、reason、weakness、suggestion 的含义自洽
""".strip()

    user_prompt = f"""
请根据以下量规，对当前学生报告的【{dimension_name}】维度进行评分。

# 当前维度评分量规

{rubric}

# 上一轮审核不通过原因

{audit_feedback_text}

# RAG 参考报告片段

{rag_context if rag_context else "[未检索到参考片段]"}

{primary_block}

# 评分任务

请比较当前学生报告的当前维度相关片段与 RAG 参考片段的质量差异，但最终分数必须基于当前学生报告本身在本维度的实际表现。

请严格输出以下 JSON 格式：

{{
  "evidence": [
    "必须来自当前学生报告相关片段的依据1",
    "必须来自当前学生报告相关片段的依据2"
  ],
  "reason": "基于上述证据和当前维度量规，说明评分理由。",
  "reference_comparison": "说明当前学生报告相较于优质报告和普通报告的大致水平差异；只能用于尺度校准，不得把参考报告内容当作学生证据，也不要复述参考报告原文。",
  "weakness": "该维度的主要不足，必须与 evidence 和 reason 保持一致。",
  "suggestion": "该维度的改进建议，必须针对 weakness 提出具体可操作建议。",
  "score": 具体整数分数
}}
""".strip()

    return system_prompt, user_prompt


# ============================================================
# 评分核心逻辑
# ============================================================

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
    student_dimension_text, student_dimension_debug = retrieve_student_dimension_text(
        report_context=merged_report_context,
        dimension_name=dimension_name,
        rubric=rubric,
        top_k=5,
    )

    rag_context, _rag_debug = retrieve_reference_context_for_dimension(
        report_context=student_dimension_text or merged_report_context,
        dimension_key=dimension_key,
        dimension_name=dimension_name,
        rubric=rubric,
        top_k=rag_top_k,
    )

    scores: List[SingleScore] = []

    for i in range(1, scoring_times + 1):
        system_prompt, user_prompt = build_dimension_scoring_prompt(
            dimension_key=dimension_key,
            dimension_name=dimension_name,
            rubric=rubric,
            merged_report_context=merged_report_context,
            student_dimension_text=student_dimension_text,
            rag_context=rag_context,
            round_index=i,
            audit_feedback=audit_feedback,
        )

        raw = llm.chat_json(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.0)

        try:
            parsed = SingleScore(**raw)
        except ValidationError:
            fixed = {
                "score": int(raw.get("score", 1)),
                "reason": str(raw.get("reason", "")),
                "evidence": raw.get("evidence", []),
                "reference_comparison": str(raw.get("reference_comparison", "")),
                "weakness": str(raw.get("weakness", "")),
                "suggestion": str(raw.get("suggestion", "")),
            }
            if not isinstance(fixed["evidence"], list):
                fixed["evidence"] = [str(fixed["evidence"])]
            fixed["score"] = max(1, min(5, fixed["score"]))
            parsed = SingleScore(**fixed)

        scores.append(parsed)

    numeric_scores = [s.score for s in scores]
    mean_score = float(statistics.mean(numeric_scores))
    std_score = float(statistics.pstdev(numeric_scores)) if len(numeric_scores) > 1 else 0.0
    min_score = float(min(numeric_scores))
    max_score = float(max(numeric_scores))
    cv: Optional[float] = std_score / mean_score if mean_score > 1e-8 else None

    consistency_level = judge_consistency(
        cv=cv,
        std=std_score,
        min_score=min_score,
        max_score=max_score,
    )
    summary_comment = summarize_dimension_scores(
        dimension_name=dimension_name,
        scores=scores,
        mean=mean_score,
        std=std_score,
        cv=cv,
        consistency_level=consistency_level,
    )

    return DimensionScoreSummary(
        dimension_key=dimension_key,
        dimension_name=dimension_name,
        student_dimension_text=student_dimension_text,
        student_dimension_debug=student_dimension_debug,
        scores=scores,
        mean=round(mean_score, 3),
        std=round(std_score, 3),
        cv=round(cv, 3) if cv is not None else None,
        min_score=round(min_score, 3),
        max_score=round(max_score, 3),
        consistency_level=consistency_level,
        summary_comment=summary_comment,
    )


def judge_consistency(
    cv: Optional[float],
    std: float,
    min_score: float,
    max_score: float,
) -> str:
    score_range = max_score - min_score
    if cv is None:
        return "较稳定" if std < 0.5 else "需复核"
    if cv < 0.10 and score_range <= 1.5:
        return "评分稳定"
    if cv < 0.20 and score_range <= 2.5:
        return "存在轻微分歧"
    return "评分不稳定，建议人工复核"


def summarize_dimension_scores(
    dimension_name: str,
    scores: List[SingleScore],
    mean: float,
    std: float,
    cv: Optional[float],
    consistency_level: str,
) -> str:
    reason_samples = [s.reason for s in scores[:3] if s.reason]
    comparison_samples = [s.reference_comparison for s in scores[:3] if s.reference_comparison]
    weakness_samples = [s.weakness for s in scores if s.weakness]
    suggestion_samples = [s.suggestion for s in scores if s.suggestion]

    reasons_text = "；".join(reason_samples) if reason_samples else "未形成明确评分理由。"
    comparison_text = "；".join(comparison_samples) if comparison_samples else "未形成明确参考样例比较。"
    weakness_text = weakness_samples[0] if weakness_samples else "未形成明确不足描述。"
    suggestion_text = suggestion_samples[0] if suggestion_samples else "建议结合量规进一步修改。"

    return (
        f"当前维度表现：{reasons_text}。"
        f"与参考样例相比：{comparison_text}。"
        f"主要不足：{weakness_text}。"
        f"改进建议：{suggestion_text}"
    )


def score_all_dimensions(
    llm: DeepSeekClient,
    merged_report_context: str,
    scoring_times: int = DEFAULT_SCORING_TIMES,
    rag_top_k: int = DEFAULT_RAG_TOP_K,
) -> tuple[Dict[str, DimensionScoreSummary], List[str]]:
    errors: List[str] = []
    results: Dict[str, DimensionScoreSummary] = {}

    if not merged_report_context:
        errors.append("merged_report_context 为空，无法评分。")
        return results, errors

    for dimension_key, dimension_name in SCORING_DIMENSIONS.items():
        try:
            results[dimension_key] = score_one_dimension(
                llm=llm,
                dimension_key=dimension_key,
                dimension_name=dimension_name,
                rubric=RUBRICS[dimension_key],
                merged_report_context=merged_report_context,
                scoring_times=scoring_times,
                rag_top_k=rag_top_k,
            )
        except Exception as exc:
            errors.append(f"{dimension_name} 评分失败：{exc}")

    return results, errors


def build_dimension_summary(
    dimension_results: Dict[str, DimensionScoreSummary],
) -> List[Dict[str, Any]]:
    return [
        {
            "dimension_key": key,
            "dimension_name": result.dimension_name,
            "mean": result.mean,
            "cv": result.cv,
            "consistency_level": result.consistency_level,
            "summary_comment": result.summary_comment,
        }
        for key, result in dimension_results.items()
    ]


def build_dimension_summary_text(
    dimension_results: Dict[str, DimensionScoreSummary],
) -> str:
    lines: List[str] = []
    for result in dimension_results.values():
        cv_text = "无" if result.cv is None else f"{result.cv:.3f}"
        lines.append(
            f"【{result.dimension_name}】\n"
            f"- 平均分：{result.mean:.2f}\n"
            f"- 差异系数 CV：{cv_text}\n"
            f"- 一致性判断：{result.consistency_level}\n"
            f"- 总结评价：{result.summary_comment}"
        )
    return "\n\n".join(lines)


def generate_final_comment_with_llm(
    llm: DeepSeekClient,
    dimension_results: Dict[str, DimensionScoreSummary],
    risk_flags: List[str],
) -> Dict[str, Any]:
    dimension_brief = {
        key: {
            "dimension_name": value.dimension_name,
            "mean": value.mean,
            "std": value.std,
            "cv": value.cv,
            "min_score": value.min_score,
            "max_score": value.max_score,
            "consistency_level": value.consistency_level,
            "summary_comment": value.summary_comment,
            "student_dimension_text": value.student_dimension_text,
        }
        for key, value in dimension_results.items()
    }

    system_prompt = """
你是一名教育评价专家。你现在只做汇总评价，不重新评分。
你必须基于已给出的四个维度统计结果，生成最终反馈。
不能修改各维度分数。
不能计算、生成或展示报告总分。
不能输出或复述 RAG 参考报告原文。
只能基于当前学生报告相关文本和各维度评分总结进行反馈。
输出必须是 JSON object，不要输出 Markdown。
""".strip()

    user_prompt = f"""
四个维度统计结果：
{json.dumps(dimension_brief, ensure_ascii=False, indent=2)}

风险标记：
{json.dumps(risk_flags, ensure_ascii=False, indent=2)}

请输出以下 JSON 格式：

{{
  "strengths": ["学生报告的主要优势1", "学生报告的主要优势2"],
  "weaknesses": ["学生报告的主要不足1", "学生报告的主要不足2"],
  "revision_suggestions": ["具体修改建议1", "具体修改建议2"],
  "final_comment": "一段完整、客观、适合反馈给学生的总评。注意不要出现报告总分。"
}}
""".strip()

    try:
        raw = llm.chat_json(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.4)
        return {
            "strengths": ensure_list(raw.get("strengths")),
            "weaknesses": ensure_list(raw.get("weaknesses")),
            "revision_suggestions": ensure_list(raw.get("revision_suggestions")),
            "final_comment": str(raw.get("final_comment", "")),
        }
    except Exception as exc:
        return {
            "strengths": [],
            "weaknesses": [],
            "revision_suggestions": [],
            "final_comment": f"最终汇总生成失败：{exc}",
        }


def aggregate_final_report(
    llm: DeepSeekClient,
    dimension_results: Dict[str, DimensionScoreSummary],
) -> FinalGradeReport:
    risk_flags: List[str] = []

    for result in dimension_results.values():
        if result.cv is not None and result.cv >= 0.20:
            risk_flags.append(
                f"{result.dimension_name} 维度 CV={result.cv}，评分分歧较大，建议人工复核。"
            )
        if result.max_score - result.min_score >= 2:
            risk_flags.append(
                f"{result.dimension_name} 维度最高分与最低分差距为 "
                f"{result.max_score - result.min_score:.1f}，建议检查报告内容是否存在歧义。"
            )
        if not result.student_dimension_text:
            risk_flags.append(
                f"{result.dimension_name} 维度未能抽取到明确的学生相关文本，建议人工检查该维度评分依据。"
            )

    final_meta = generate_final_comment_with_llm(llm, dimension_results, risk_flags)

    return FinalGradeReport(
        dimension_summary=build_dimension_summary(dimension_results),
        dimension_summary_text=build_dimension_summary_text(dimension_results),
        dimension_results=dimension_results,
        strengths=final_meta.get("strengths", []),
        weaknesses=final_meta.get("weaknesses", []),
        revision_suggestions=final_meta.get("revision_suggestions", []),
        risk_flags=risk_flags,
        final_comment=final_meta.get("final_comment", ""),
    )


def _collect_evidence_text(dimension_results: Dict[str, DimensionScoreSummary]) -> str:
    evidence_items: List[str] = []
    seen: set[str] = set()

    for result in dimension_results.values():
        for single in result.scores:
            for item in single.evidence:
                text = str(item).strip()
                if text and text not in seen:
                    seen.add(text)
                    evidence_items.append(text)

    if evidence_items:
        return "；".join(evidence_items[:12])

    fallback_blocks: List[str] = []
    for result in dimension_results.values():
        snippet = (result.student_dimension_text or "").strip()
        if snippet:
            fallback_blocks.append(f"【{result.dimension_name}】{snippet[:300]}")
    if fallback_blocks:
        return "\n".join(fallback_blocks[:4])

    return "未能从报告中抽取到明确的创造性思维相关证据。"


def _build_feedback_text(final_report: FinalGradeReport) -> str:
    parts: List[str] = []

    if final_report.final_comment:
        parts.append(final_report.final_comment)

    if final_report.strengths:
        parts.append("主要优势：" + "；".join(final_report.strengths))

    if final_report.weaknesses:
        parts.append("主要不足：" + "；".join(final_report.weaknesses))

    if final_report.revision_suggestions:
        parts.append("改进建议：" + "；".join(final_report.revision_suggestions))

    if final_report.risk_flags:
        parts.append("风险提示：" + "；".join(final_report.risk_flags))

    if not parts and final_report.dimension_summary_text:
        parts.append(final_report.dimension_summary_text)

    return "\n".join(parts).strip() or "未生成有效反馈。"


def _compute_overall_score(dimension_results: Dict[str, DimensionScoreSummary]) -> float:
    if not dimension_results:
        return 0.0
    means = [result.mean for result in dimension_results.values()]
    return round(float(statistics.mean(means)), 2)


def to_unified_output(final_report: FinalGradeReport) -> CreativityEvaluationResult:
    """将内部完整报告转换为统一对外 JSON 格式。"""
    return {
        "score": _compute_overall_score(final_report.dimension_results),
        "feedback": _build_feedback_text(final_report),
        "evidence": _collect_evidence_text(final_report.dimension_results),
    }


# ============================================================
# 对外统一接口
# ============================================================

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
    if not (report_text or "").strip():
        return {
            "score": 0.0,
            "feedback": "报告文本为空，无法进行创造性思维评分。",
            "evidence": "",
        }

    llm = DeepSeekClient(api_key=api_key, model=model)
    merged_report_context = build_merged_report_context(report_text)

    dimension_results, errors = score_all_dimensions(
        llm=llm,
        merged_report_context=merged_report_context,
        scoring_times=scoring_times,
        rag_top_k=rag_top_k,
    )

    if not dimension_results:
        return {
            "score": 0.0,
            "feedback": "创造性思维评分失败。" + ("；".join(errors) if errors else ""),
            "evidence": "",
        }

    final_report = aggregate_final_report(llm=llm, dimension_results=dimension_results)
    unified = to_unified_output(final_report)

    if errors:
        unified["feedback"] = unified["feedback"] + "\n[警告] " + "；".join(errors)

    return unified


# 别名，便于与其他 agent 统一调用风格
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
    llm = DeepSeekClient(model=model)
    merged_report_context = build_merged_report_context(report_text)
    dimension_results, errors = score_all_dimensions(
        llm=llm,
        merged_report_context=merged_report_context,
        scoring_times=scoring_times,
        rag_top_k=rag_top_k,
    )

    final_report_dict: Dict[str, Any] = {}
    if dimension_results:
        final_report = aggregate_final_report(llm=llm, dimension_results=dimension_results)
        final_report_dict = final_report.model_dump()

    return {
        "model": model,
        "scoring_times_per_dimension": scoring_times,
        "rag_top_k_per_dimension": rag_top_k,
        "merged_report_context": merged_report_context,
        "final_report": final_report_dict,
        "dimension_results": {
            key: value.model_dump() for key, value in dimension_results.items()
        },
        "unified_output": to_unified_output(
            FinalGradeReport(**final_report_dict)
        ) if final_report_dict else {"score": 0.0, "feedback": "", "evidence": ""},
        "errors": errors,
    }


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
