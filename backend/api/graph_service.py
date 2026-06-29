"""LangGraph 调用封装（不修改 agents/ 下现有实现）。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 项目根目录（empty-window）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SUPPORTED_EVALUATION_MODES = ("route", "pbl_report", "section_report")


def format_pbl_state_response(state: dict[str, Any]) -> dict[str, Any]:
    """将 PBL 图 state 格式化为 /group-evaluation 兼容的响应体。"""
    group_results = state.get("group_project_results") or {}
    creativity = group_results.get("creativity") or {}
    critical = group_results.get("critical") or {}
    problemsolving = group_results.get("problemsolving") or {}

    return {
        "evaluation_mode": state.get("evaluation_mode") or "pbl_report",
        "creativity": creativity,
        "critical": critical,
        "problemsolving": problemsolving,
        "dimension_summary": list(state.get("dimension_summary") or []),
        "primary_indicator_summary": list(state.get("primary_indicator_summary") or []),
        "final_score": state.get("total_score"),
        "dimension_mean_score": state.get("dimension_mean_score"),
        "final_feedback": state.get("final_feedback"),
        "final_comment": state.get("final_comment") or state.get("final_feedback"),
        "strengths": list(state.get("pbl_strengths") or []),
        "weaknesses": list(state.get("pbl_weaknesses") or []),
        "revision_suggestions": list(state.get("pbl_revision_suggestions") or []),
        "audit_passed": bool(state.get("audit_passed")),
        "audit_status": state.get("audit_status") or "",
        "max_review_rounds_reached": bool(state.get("max_review_rounds_reached")),
        "output_mode": state.get("output_mode") or "",
        "internal_audit": dict(state.get("internal_audit") or {}),
        "errors": list(state.get("pbl_errors") or []),
        "last_saved_evaluation_id": state.get("last_saved_evaluation_id") or "",
        "memory_context": state.get("memory_context"),
    }


def run_langgraph_analysis(
    student_input: str,
    *,
    uploaded_files: list[dict[str, Any]] | None = None,
    routes: list[str] | None = None,
    student_id: str | None = None,
    memory_retrieve_k: int = 3,
    enable_deep_research: bool | None = None,
    session_id: str | None = None,
    self_score: float | None = None,
) -> dict[str, Any]:
    """调用 LangGraph 工作流，返回可 JSON 序列化的 dict。"""
    import llm_config  # noqa: F401
    from llm_config import is_dotenv_loaded

    if not is_dotenv_loaded():
        raise ValueError(
            "未配置 LLM API Key。请在项目根目录 .env 中设置 DeepSeek/OpenAI 密钥（OPENAI_API_KEY 或 LLM_API_KEY）。"
        )

    from fastapi.encoders import jsonable_encoder
    from main_graph import app as langgraph_app
    from state import create_initial_state

    # API 默认关闭 Deep Research，避免博查/多页抓取导致超时或 500
    if enable_deep_research is None:
        enable_deep_research = False

    initial = create_initial_state(
        student_input,
        uploaded_files=uploaded_files,
        routes=routes,
        student_id=student_id,
        session_id=session_id,
        memory_retrieve_k=memory_retrieve_k,
        enable_deep_research=enable_deep_research,
        evaluation_mode="route",
        self_score=self_score,
    )

    logger.info(
        "LangGraph invoke start (routes=%s, deep_research=%s, input_len=%d)",
        initial.get("routes"),
        enable_deep_research,
        len(student_input),
    )

    result = langgraph_app.invoke(initial)

    logger.info("LangGraph invoke done")
    return jsonable_encoder(dict(result))


def run_pbl_analysis(
    report_text: str,
    *,
    student_id: str | None = None,
    session_id: str | None = None,
    uploaded_files: list[dict[str, Any]] | None = None,
    enable_pbl_review: bool = False,
    pbl_scoring_times: int | None = None,
    pbl_rag_top_k: int | None = None,
    pbl_review_rounds: int | None = None,
    memory_retrieve_k: int = 3,
    use_cache: bool = True,
) -> dict[str, Any]:
    """
    调用 PBL 主图（记忆检索 → 小组评价 → 持久化），返回 API 兼容 dict。

    PBL 分数尺度为 1.0–5.0（与四路由 0–100 不同，见 evaluation_mode）。
    """
    import llm_config  # noqa: F401
    from agents.group_project.pbl_config import (
        DEFAULT_RAG_TOP_K,
        DEFAULT_REVIEW_ROUNDS,
        DEFAULT_SCORING_TIMES,
    )
    from llm_config import is_dotenv_loaded
    from services.pbl_evaluation_cache import (
        build_cache_key,
        get_cached_evaluation,
        set_cached_evaluation,
    )

    if not is_dotenv_loaded():
        raise ValueError(
            "未配置 LLM API Key。请在项目根目录 .env 中设置 DeepSeek/OpenAI 密钥（OPENAI_API_KEY 或 LLM_API_KEY）。"
        )

    from fastapi.encoders import jsonable_encoder
    from pbl_main_graph import pbl_app
    from state import create_pbl_initial_state

    text = (report_text or "").strip()
    if not text:
        raise ValueError("report_text 不能为空")

    scoring_times = max(1, int(pbl_scoring_times or DEFAULT_SCORING_TIMES))
    rag_top_k = max(1, int(pbl_rag_top_k or DEFAULT_RAG_TOP_K))
    review_rounds = max(0, int(pbl_review_rounds or DEFAULT_REVIEW_ROUNDS))

    cache_key = build_cache_key(
        text,
        enable_review=enable_pbl_review,
        scoring_times=scoring_times,
        rag_top_k=rag_top_k,
        review_rounds=review_rounds,
    )
    if use_cache and not (student_id or "").strip():
        cached = get_cached_evaluation(cache_key)
        if cached:
            logger.info("PBL cache hit (key=%s...)", cache_key[:12])
            payload = dict(cached)
            payload["cache_hit"] = True
            return jsonable_encoder(payload)

    initial = create_pbl_initial_state(
        text,
        uploaded_files=uploaded_files,
        student_id=student_id,
        session_id=session_id,
        enable_pbl_review=enable_pbl_review,
        pbl_scoring_times=scoring_times,
        pbl_rag_top_k=rag_top_k,
        pbl_review_rounds=review_rounds,
        memory_retrieve_k=memory_retrieve_k,
    )

    logger.info(
        "PBL graph invoke start (review=%s, student_id=%s, input_len=%d, scoring_times=%d)",
        enable_pbl_review,
        (student_id or "").strip() or "(none)",
        len(text),
        scoring_times,
    )

    result = pbl_app.invoke(initial)
    payload = format_pbl_state_response(dict(result))
    payload["cache_hit"] = False

    if use_cache and not (student_id or "").strip():
        set_cached_evaluation(cache_key, payload)

    logger.info(
        "PBL graph invoke done (final_score=%s, saved=%s, cache=%s)",
        payload.get("final_score"),
        payload.get("last_saved_evaluation_id"),
        use_cache,
    )
    return jsonable_encoder(payload)


def format_section_state_response(state: dict[str, Any]) -> dict[str, Any]:
    """将章节反馈图 state 格式化为 /section-evaluation 兼容响应体。"""
    section_summary = dict(state.get("section_summary") or {})
    return {
        "evaluation_mode": state.get("evaluation_mode") or "section_report",
        "section_target": (state.get("section_target") or "").strip() or None,
        "section_texts": dict(state.get("section_texts") or {}),
        "section_results": list(state.get("section_results") or []),
        "section_summary": section_summary,
        "section_skipped": list(state.get("section_skipped") or []),
        "section_errors": list(state.get("section_errors") or []),
        "section_parse_warnings": list(state.get("section_parse_warnings") or []),
        "unmatched_text": state.get("unmatched_text") or "",
        "graphrag_backend": state.get("graphrag_backend") or "",
        "overall_score": section_summary.get("overall_score"),
        "section_scores": dict(section_summary.get("section_scores") or {}),
        "final_score": state.get("total_score"),
        "final_feedback": state.get("final_feedback") or section_summary.get("overall_comment"),
        "final_comment": state.get("final_comment") or section_summary.get("overall_comment"),
        "last_saved_evaluation_id": state.get("last_saved_evaluation_id") or "",
        "memory_context": state.get("memory_context"),
    }


def run_section_analysis(
    report_text: str,
    *,
    section_name: str | None = None,
    section_texts: dict[str, str] | None = None,
    student_id: str | None = None,
    session_id: str | None = None,
    uploaded_files: list[dict[str, Any]] | None = None,
    enable_section_review: bool = True,
    section_scoring_times: int | None = None,
    section_review_rounds: int | None = None,
    section_cv_threshold: float | None = None,
    memory_retrieve_k: int = 3,
) -> dict[str, Any]:
    """
    调用章节反馈主图（记忆检索 → 切分 → 评价 → 汇总 → 持久化）。

    分数尺度为 1.0–5.0（evaluation_mode=section_report）。
    """
    import llm_config  # noqa: F401
    from agents.section_report.section_config import (
        DEFAULT_CV_THRESHOLD,
        DEFAULT_MAX_REVIEW_ROUNDS,
    )
    from llm_config import is_dotenv_loaded

    if not is_dotenv_loaded():
        raise ValueError(
            "未配置 LLM API Key。请在项目根目录 .env 中设置 DeepSeek/OpenAI 密钥（OPENAI_API_KEY 或 LLM_API_KEY）。"
        )

    from fastapi.encoders import jsonable_encoder
    from section_main_graph import section_app
    from state import create_section_initial_state

    text = (report_text or "").strip()
    if not text and not section_texts:
        raise ValueError("report_text 不能为空")

    initial = create_section_initial_state(
        text,
        section_name=section_name,
        section_texts=section_texts,
        uploaded_files=uploaded_files,
        student_id=student_id,
        session_id=session_id,
        enable_section_review=enable_section_review,
        section_scoring_times=section_scoring_times,
        section_review_rounds=section_review_rounds or DEFAULT_MAX_REVIEW_ROUNDS,
        section_cv_threshold=section_cv_threshold or DEFAULT_CV_THRESHOLD,
        memory_retrieve_k=memory_retrieve_k,
    )

    logger.info(
        "Section graph invoke start (target=%s, student_id=%s, input_len=%d, review=%s)",
        (section_name or "").strip() or "ALL",
        (student_id or "").strip() or "(none)",
        len(text),
        enable_section_review,
    )

    result = section_app.invoke(initial)
    payload = format_section_state_response(dict(result))

    logger.info(
        "Section graph invoke done (overall_score=%s, sections=%d, saved=%s)",
        payload.get("overall_score"),
        len(payload.get("section_results") or []),
        payload.get("last_saved_evaluation_id"),
    )
    return jsonable_encoder(payload)


__all__ = [
    "PROJECT_ROOT",
    "SUPPORTED_EVALUATION_MODES",
    "format_pbl_state_response",
    "format_section_state_response",
    "run_langgraph_analysis",
    "run_pbl_analysis",
    "run_section_analysis",
]
