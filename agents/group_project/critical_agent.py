"""
批判性思维评分 Agent（从 preview-agent 迁移）。

对项目报告按 4 个二级指标（证据分析、数据分析、逻辑推演、局限性评价）进行
10 次独立采样评分，保留原有量规、片段抽取、RAG 对照与汇总逻辑。

对外统一接口：
    evaluate_critical(report_text: str) -> {"score": float, "feedback": str, "evidence": str}
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


class CriticalEvaluationResult(TypedDict):
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

    if dimension_name in chunk_text:
        score += 8

    for kw in keywords:
        if kw in chunk_text:
            score += 3 if len(kw) >= 4 else 1

    evidence_markers = [
        "如图", "表", "数据", "实验", "结果", "分析", "结论", "原因", "说明", "可见",
        "可以看出", "因此", "所以", "文献", "理论", "公式", "模型", "假设", "局限",
        "边界", "误差", "标准差", "拟合", "对比", "前提", "因果", "相关", "推论",
        "可靠性", "适用范围", "改进",
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
    chunks = split_report_into_chunks(report_context, max_chunk_chars, 120)
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

    return "未能从报告中抽取到明确的批判性思维相关证据。"


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


def to_unified_output(final_report: FinalGradeReport) -> CriticalEvaluationResult:
    return {
        "score": _compute_overall_score(final_report.dimension_results),
        "feedback": _build_feedback_text(final_report),
        "evidence": _collect_evidence_text(final_report.dimension_results),
    }


# ============================================================
# 对外统一接口
# ============================================================

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
    if not (report_text or "").strip():
        return {
            "score": 0.0,
            "feedback": "报告文本为空，无法进行批判性思维评分。",
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
            "feedback": "批判性思维评分失败。" + ("；".join(errors) if errors else ""),
            "evidence": "",
        }

    final_report = aggregate_final_report(llm=llm, dimension_results=dimension_results)
    unified = to_unified_output(final_report)

    if errors:
        unified["feedback"] = unified["feedback"] + "\n[警告] " + "；".join(errors)

    return unified


# 别名，便于与其他 agent 统一调用风格
evaluate = evaluate_critical


def run_grading_from_text(
    report_text: str,
    *,
    model: str = DEFAULT_MODEL,
    scoring_times: int = DEFAULT_SCORING_TIMES,
    rag_top_k: int = DEFAULT_RAG_TOP_K,
) -> Dict[str, Any]:
    """兼容 preview-agent 风格的完整结果。对外推荐使用 evaluate_critical()。"""
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
