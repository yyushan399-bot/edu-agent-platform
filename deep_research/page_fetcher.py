"""抓取网页 HTML（打开网页）。"""

from __future__ import annotations

import requests

from deep_research.config import DEFAULT_FETCH_TIMEOUT, DEFAULT_MAX_PAGE_CHARS

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def fetch_page_html(url: str, *, timeout: int = DEFAULT_FETCH_TIMEOUT) -> str:
    """GET 请求获取网页 HTML。"""
    response = requests.get(
        url,
        headers=DEFAULT_HEADERS,
        timeout=timeout,
        allow_redirects=True,
    )
    response.raise_for_status()
    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding or "utf-8"
    text = response.text
    if len(text) > DEFAULT_MAX_PAGE_CHARS:
        text = text[:DEFAULT_MAX_PAGE_CHARS]
    return text


__all__ = ["fetch_page_html"]
