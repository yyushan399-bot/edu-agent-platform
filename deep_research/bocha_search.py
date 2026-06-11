"""博查 BochaAI Web Search API。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from deep_research.config import BOCHA_WEB_SEARCH_URL, DEFAULT_SEARCH_COUNT, get_bocha_api_key


@dataclass
class SearchHit:
    """单条搜索结果。"""

    title: str
    url: str
    snippet: str
    summary: str


def _parse_hits(payload: dict[str, Any]) -> list[SearchHit]:
    data = payload.get("data") or payload
    web_pages = data.get("webPages") or data.get("web_pages") or {}
    items = web_pages.get("value") or web_pages.get("results") or []
    hits: list[SearchHit] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or item.get("link") or "").strip()
        if not url:
            continue
        hits.append(
            SearchHit(
                title=(item.get("name") or item.get("title") or "").strip(),
                url=url,
                snippet=(item.get("snippet") or "").strip(),
                summary=(item.get("summary") or item.get("snippet") or "").strip(),
            )
        )
    return hits


def bocha_web_search(
    query: str,
    *,
    count: int = DEFAULT_SEARCH_COUNT,
    summary: bool = True,
    freshness: str = "noLimit",
    api_key: str | None = None,
) -> list[SearchHit]:
    """调用博查 web-search，返回结构化结果列表。"""
    key = api_key or get_bocha_api_key()
    if not key:
        raise ValueError("未配置 BOCHA_API_KEY，无法执行博查搜索。")

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    body = {
        "query": query,
        "count": min(max(count, 1), 50),
        "summary": summary,
        "freshness": freshness,
    }
    response = requests.post(
        BOCHA_WEB_SEARCH_URL,
        headers=headers,
        json=body,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    code = payload.get("code")
    if code is not None and code not in (0, 200, "0", "200"):
        message = payload.get("message") or payload.get("msg") or str(payload)
        raise RuntimeError(f"博查搜索失败: {message}")

    return _parse_hits(payload)


__all__ = ["SearchHit", "bocha_web_search"]
