"""清洗网页正文。"""

from __future__ import annotations

import re

_NOISE_LINE = re.compile(
    r"^(版权所有|Copyright|ICP|登录|注册|扫码|关注公众号|相关阅读|推荐阅读|"
    r"上一篇|下一篇|分享到|点击收藏|广告|免责声明).*$",
    re.IGNORECASE,
)


def clean_text(text: str, *, max_chars: int = 8000) -> str:
    """去噪、合并空白、截断。"""
    if not text:
        return ""
    lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) < 2:
            continue
        if _NOISE_LINE.match(line):
            continue
        if re.fullmatch(r"[\d\W_]+", line):
            continue
        lines.append(line)

    merged = "\n".join(lines)
    merged = re.sub(r"\n{3,}", "\n\n", merged)
    merged = re.sub(r"[ \t]{2,}", " ", merged)
    if len(merged) > max_chars:
        merged = merged[:max_chars] + "\n…（正文已截断）"
    return merged.strip()


__all__ = ["clean_text"]
