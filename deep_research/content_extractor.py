"""从 HTML 提取正文。"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

_STRIP_TAGS = {"script", "style", "noscript", "iframe", "svg", "header", "footer", "nav"}


def extract_main_text(html: str) -> str:
    """提取网页主体文本。"""
    if not (html or "").strip():
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()

    for selector in ("article", "main", "[role=main]"):
        node = soup.select_one(selector)
        if node:
            text = node.get_text(separator="\n", strip=True)
            if len(text) > 200:
                return text

    body = soup.body or soup
    return body.get_text(separator="\n", strip=True)


def extract_title(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return ""


__all__ = ["extract_main_text", "extract_title"]
