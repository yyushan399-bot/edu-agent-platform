"""PBL 小组项目评价结果文件缓存。"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from agents.group_project.pbl_config import (
    PBL_CACHE_DIR,
    PBL_CACHE_ENABLED,
    PBL_CACHE_TTL_HOURS,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_cache_dir() -> Path:
    path = Path(PBL_CACHE_DIR)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_cache_key(
    report_text: str,
    *,
    enable_review: bool,
    scoring_times: int,
    rag_top_k: int,
    review_rounds: int,
) -> str:
    """根据报告内容与评价参数生成稳定缓存键。"""
    payload = "|".join(
        [
            (report_text or "").strip(),
            str(bool(enable_review)),
            str(int(scoring_times)),
            str(int(rag_top_k)),
            str(int(review_rounds)),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_path(key: str) -> Path:
    safe = "".join(c for c in key if c.isalnum())
    return _resolve_cache_dir() / f"{safe}.json"


def get_cached_evaluation(key: str) -> dict[str, Any] | None:
    if not PBL_CACHE_ENABLED:
        return None
    path = _cache_path(key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        created_at = float(data.get("created_at") or 0)
        if PBL_CACHE_TTL_HOURS > 0 and created_at > 0:
            age_hours = (time.time() - created_at) / 3600.0
            if age_hours > PBL_CACHE_TTL_HOURS:
                return None
        result = data.get("result")
        return dict(result) if isinstance(result, dict) else None
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def set_cached_evaluation(key: str, payload: dict[str, Any]) -> None:
    if not PBL_CACHE_ENABLED:
        return
    record = {
        "cache_key": key,
        "created_at": time.time(),
        "result": payload,
    }
    path = _cache_path(key)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


__all__ = [
    "PBL_CACHE_ENABLED",
    "build_cache_key",
    "get_cached_evaluation",
    "set_cached_evaluation",
]
