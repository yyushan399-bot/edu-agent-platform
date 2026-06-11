"""图片 OCR：使用 PaddleOCR 提取文字。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}

_ocr_engine: Any | None = None


def _get_ocr_engine() -> Any:
    global _ocr_engine
    if _ocr_engine is None:
        from paddleocr import PaddleOCR

        _ocr_engine = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
    return _ocr_engine


def _lines_from_ocr_result(result: list | None) -> list[str]:
    """从 PaddleOCR 返回结构中抽取文本行。"""
    if not result:
        return []
    lines: list[str] = []
    for page in result:
        if not page:
            continue
        for item in page:
            if not item or len(item) < 2:
                continue
            text_part = item[1]
            if isinstance(text_part, (list, tuple)) and text_part:
                line = str(text_part[0]).strip()
            elif isinstance(text_part, str):
                line = text_part.strip()
            else:
                continue
            if line:
                lines.append(line)
    return lines


def parse_image_text(image_path: str | Path) -> str:
    """对 PNG/JPG/JPEG 执行 OCR，返回识别文本。"""
    path = Path(image_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"图片不存在: {path}")
    suffix = path.suffix.lower()
    if suffix not in IMAGE_SUFFIXES:
        raise ValueError(f"仅支持 {', '.join(sorted(IMAGE_SUFFIXES))} 图片: {path}")

    ocr = _get_ocr_engine()
    result = ocr.ocr(str(path), cls=True)
    lines = _lines_from_ocr_result(result)
    return "\n".join(lines)
