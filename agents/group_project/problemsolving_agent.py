"""
问题解决能力评分 Agent（从 preview-agent 迁移）。

对项目报告按 4 个二级指标（问题界定、方案建构、方案实施、反思调节）进行
10 次独立采样评分，保留原有量规、片段抽取、RAG 对照与汇总逻辑。

对外统一接口：
    evaluate_problemsolving(report_text: str) -> {"score": float, "feedback": str, "evidence": str}
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


class ProblemSolvingEvaluationResult(TypedDict):
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
# 工具函数
# ============================================================

def format_student_report_sections(
    *,
    dimension_name: str,
    student_dimension_text: str,
) -> str:
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


PROBLEMSOLVING_DIMENSION_STRONG_KEYWORDS = {
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


PROBLEMSOLVING_DIMENSION_EXCLUDE_HINTS = {
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
            "局限", "改进方向", "具体改法", "怎么改", "可操作",
            "预期效果", "增加实验次数", "改进装置", "优化流程",
        ],
    }
    keywords = list(base_keywords.get(dimension_name, []))
    rubric_text = rubric or ""
    candidate_terms = re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", rubric_text)
    stop_terms = {
        "评分", "量规", "报告", "学生", "当前", "维度", "进行", "能够", "没有", "缺少",
        "清晰", "明确", "具体", "基本", "严重", "完全", "相关", "内容", "情况", "之间",
        "部分", "分析", "评价",
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

    strong_keywords = PROBLEMSOLVING_DIMENSION_STRONG_KEYWORDS.get(dimension_name, [])
    exclude_hints = PROBLEMSOLVING_DIMENSION_EXCLUDE_HINTS.get(dimension_name, [])

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


def retrieve_student_dimension_text(
    report_context: str,
    dimension_name: str,
    rubric: str,
    top_k: int = 5,
    max_chunk_chars: int = 450,
) -> tuple[str, Dict[str, Any]]:
    cleaned_report_context = clean_report_context_for_student_chunks(report_context)
    chunks = split_report_into_chunks(cleaned_report_context, max_chunk_chars, 60)
    keywords = extract_keywords_for_dimension(dimension_name, rubric)

    scored_chunks: List[Dict[str, Any]] = []
    for chunk in chunks:
        score = score_student_chunk_relevance(chunk["text"], dimension_name, rubric, keywords)
        scored_chunks.append({**chunk, "score": score})

    scored_chunks.sort(key=lambda x: x["score"], reverse=True)
    selected_chunks = [item for item in scored_chunks if item["score"] > 0][:top_k]
    if not selected_chunks:
        selected_chunks = scored_chunks[: min(top_k, len(scored_chunks))]

    blocks = []
    for i, item in enumerate(selected_chunks, 1):
        blocks.append(
            f"【学生报告{dimension_name}相关片段 {i}】\n"
            f"片段ID：{item['chunk_id']}\n相关性分数：{item['score']}\n原文：\n{item['text']}"
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
        rag_debug.update(
            {
                "enabled": True,
                "dimension_key": dimension_key,
                "dimension_name": dimension_name,
                "top_k": top_k,
            }
        )
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
作为一名资深大学物理项目化学习实践专家，你的职责是根据评价量规，对大一工科班学生设计的项目化学习报告评分。你需要根据项目报告【{dimension_name}】维度的情况，对学生的项目报告给出1到5之间的分数。

你必须遵守：
1. 只评价当前维度：{dimension_name}
2. 评分范围为1-5分整数
3. 必须基于当前学生报告（优先「当前维度相关片段」，必要时查阅「完整报告补充」）进行判断
4. 评分首要依据是「当前学生报告相关片段」；「完整报告补充」仅用于片段不足时核对上下文，不得用其他维度的内容抬高本维分数
5. RAG 参考片段只作为评分标尺和对照样例，不能把参考报告内容当作当前学生报告内容
6. 评分证据 evidence 必须来自当前学生报告，不能来自 RAG 参考报告
7. 不要编造当前学生报告中不存在的内容
8. 如果当前学生报告没有体现某项能力，应明确指出缺失，而不是根据参考片段补充
9. 输出必须是 JSON object，不要输出 Markdown
10. 本次是第 {round_index} 次独立评分，请独立判断，不要假设其他评分结果
11. 如果提供了“上一轮审核不通过原因”，你必须在本次评分时重点修正这些问题
12. 不要机械迎合审核意见，最终仍必须基于学生报告相关片段/补充全文与当前维度量规进行独立评分
13. 如果上一轮问题是证据不可追溯，本次 evidence 必须尽量引用「当前维度相关片段」中的原文短句
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
请比较当前学生报告的当前维度相关片段与 RAG 参考片段的质量差异。最终分数必须基于当前学生报告在本维度的实际表现。

# 输出格式
请严格输出以下 JSON 格式：
{{
  "evidence": ["依据1", "依据2"],
  "reason": "评分理由",
  "reference_comparison": "与参考片段的质量差异说明",
  "weakness": "主要不足",
  "suggestion": "改进建议",
  "score": 整数分数
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
        merged_report_context, dimension_name, rubric, top_k=5
    )
    rag_context, _rag_debug = retrieve_reference_context_for_dimension(
        student_dimension_text or merged_report_context,
        dimension_key,
        dimension_name,
        rubric,
        rag_top_k,
    )

    scores: List[SingleScore] = []
    for i in range(1, scoring_times + 1):
        sys_p, usr_p = build_dimension_scoring_prompt(
            dimension_key,
            dimension_name,
            rubric,
            merged_report_context,
            student_dimension_text,
            rag_context,
            i,
            audit_feedback,
        )
        raw = llm.chat_json(sys_p, usr_p, temperature=0.0)
        try:
            parsed = SingleScore(**raw)
        except ValidationError:
            fixed = {
                "score": max(1, min(5, int(raw.get("score", 1)))),
                "reason": str(raw.get("reason", "")),
                "evidence": raw.get("evidence", []),
                "reference_comparison": str(raw.get("reference_comparison", "")),
                "weakness": str(raw.get("weakness", "")),
                "suggestion": str(raw.get("suggestion", "")),
            }
            if not isinstance(fixed["evidence"], list):
                fixed["evidence"] = [str(fixed["evidence"])]
            parsed = SingleScore(**fixed)
        scores.append(parsed)

    numeric_scores = [s.score for s in scores]
    mean_score = float(statistics.mean(numeric_scores))
    std_score = float(statistics.pstdev(numeric_scores)) if len(numeric_scores) > 1 else 0.0
    min_score = float(min(numeric_scores))
    max_score = float(max(numeric_scores))
    cv: Optional[float] = std_score / mean_score if mean_score > 1e-8 else None

    consistency_level = judge_consistency(cv, std_score, min_score, max_score)
    summary_comment = summarize_dimension_scores(
        dimension_name, scores, mean_score, std_score, cv, consistency_level
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

    return "未能从报告中抽取到明确的问题解决相关证据。"


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


def to_unified_output(final_report: FinalGradeReport) -> ProblemSolvingEvaluationResult:
    return {
        "score": _compute_overall_score(final_report.dimension_results),
        "feedback": _build_feedback_text(final_report),
        "evidence": _collect_evidence_text(final_report.dimension_results),
    }


# ============================================================
# 对外统一接口
# ============================================================

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
    if not (report_text or "").strip():
        return {
            "score": 0.0,
            "feedback": "报告文本为空，无法进行问题解决能力评分。",
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
            "feedback": "问题解决能力评分失败。" + ("；".join(errors) if errors else ""),
            "evidence": "",
        }

    final_report = aggregate_final_report(llm=llm, dimension_results=dimension_results)
    unified = to_unified_output(final_report)

    if errors:
        unified["feedback"] = unified["feedback"] + "\n[警告] " + "；".join(errors)

    return unified


# 别名，便于与其他 agent 统一调用风格
evaluate = evaluate_problemsolving


def run_grading_from_text(
    report_text: str,
    *,
    model: str = DEFAULT_MODEL,
    scoring_times: int = DEFAULT_SCORING_TIMES,
    rag_top_k: int = DEFAULT_RAG_TOP_K,
) -> Dict[str, Any]:
    """兼容 preview-agent 风格的完整结果。对外推荐使用 evaluate_problemsolving()。"""
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
