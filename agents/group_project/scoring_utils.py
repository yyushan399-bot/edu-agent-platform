"""PBL 评分共享文本 / JSON / RAG 工具函数。"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from agents.group_project.pbl_config import DEFAULT_RAG_TOP_K

try:
    from services.rag_service import retrieve_rag_context_auto
except Exception:
    retrieve_rag_context_auto = None


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


def extract_keywords_from_rubric(
    dimension_name: str,
    rubric: str,
    base_keywords: Dict[str, List[str]],
) -> List[str]:
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


def retrieve_student_dimension_text(
    report_context: str,
    dimension_name: str,
    rubric: str,
    *,
    top_k: int = 5,
    max_chunk_chars: int = 800,
    extract_keywords_fn: Callable[[str, str], List[str]],
    score_chunk_fn: Callable[[str, str, str, List[str]], int],
    preprocess_context_fn: Callable[[str], str] | None = None,
) -> Tuple[str, Dict[str, Any]]:
    context = preprocess_context_fn(report_context) if preprocess_context_fn else report_context
    chunks = split_report_into_chunks(context, max_chunk_chars, 120)
    keywords = extract_keywords_fn(dimension_name, rubric)

    scored_chunks: List[Dict[str, Any]] = []
    for chunk in chunks:
        score = score_chunk_fn(chunk["text"], dimension_name, rubric, keywords)
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
) -> Tuple[str, Dict[str, Any]]:
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
    except BaseException as exc:
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
    scores: List[Any],
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


def build_dimension_summary(
    dimension_results: Dict[str, Any],
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


def build_dimension_summary_text(dimension_results: Dict[str, Any]) -> str:
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


__all__ = [
    "build_dimension_summary",
    "build_dimension_summary_text",
    "build_merged_report_context",
    "ensure_list",
    "extract_keywords_from_rubric",
    "format_audit_feedback_for_prompt",
    "format_student_report_sections",
    "judge_consistency",
    "retrieve_reference_context_for_dimension",
    "retrieve_student_dimension_text",
    "safe_json_loads",
    "split_report_into_chunks",
    "summarize_dimension_scores",
    "truncate_text",
]
