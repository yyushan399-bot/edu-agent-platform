"""Deep Research 全流程编排。"""

from __future__ import annotations

import logging

from deep_research.bocha_search import SearchHit, bocha_web_search
from deep_research.config import DEFAULT_MAX_PAGES, DEFAULT_SEARCH_COUNT, is_deep_research_enabled
from deep_research.content_cleaner import clean_text
from deep_research.content_extractor import extract_main_text, extract_title
from deep_research.page_fetcher import fetch_page_html
from deep_research.page_summarizer import merge_page_summaries, summarize_page
from deep_research.query_generator import generate_research_queries

logger = logging.getLogger(__name__)

EMPTY_RESEARCH = "（未启用深度联网研究或未检索到可用资料。）"


def _dedupe_hits(hits: list[SearchHit], limit: int) -> list[SearchHit]:
    seen: set[str] = set()
    result: list[SearchHit] = []
    for hit in hits:
        url = hit.url.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        result.append(hit)
        if len(result) >= limit:
            break
    return result


def _process_one_page(hit: SearchHit) -> str:
    """打开网页 → 提取 → 清洗 → LLM 单页总结。"""
    try:
        html = fetch_page_html(hit.url)
        raw = extract_main_text(html)
        cleaned = clean_text(raw)
        if not cleaned and hit.summary:
            cleaned = clean_text(hit.summary)
        title = extract_title(html) or hit.title
        return summarize_page(title, cleaned)
    except Exception as exc:
        logger.warning("页面处理失败 %s: %s", hit.url, exc)
        if hit.summary:
            return summarize_page(hit.title, clean_text(hit.summary))
        return ""


def run_deep_research(
    student_input: str,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    search_count: int = DEFAULT_SEARCH_COUNT,
) -> str:
    """
    执行 Deep Research，返回 research_context（仅摘要，不含网页原文）。
    """
    if not is_deep_research_enabled():
        return EMPTY_RESEARCH

    text = (student_input or "").strip()
    if not text:
        return EMPTY_RESEARCH

    queries = generate_research_queries(text)
    all_hits: list[SearchHit] = []
    for query in queries:
        try:
            hits = bocha_web_search(query, count=search_count)
            all_hits.extend(hits)
        except Exception as exc:
            logger.warning("博查搜索失败 query=%s: %s", query, exc)

    selected = _dedupe_hits(all_hits, max_pages)
    if not selected:
        return EMPTY_RESEARCH

    page_summaries: list[str] = []
    for hit in selected:
        summary = _process_one_page(hit)
        if summary:
            page_summaries.append(summary)

    if not page_summaries:
        return EMPTY_RESEARCH

    merged = merge_page_summaries(text, page_summaries)
    return merged.strip() or EMPTY_RESEARCH


__all__ = ["EMPTY_RESEARCH", "run_deep_research"]
