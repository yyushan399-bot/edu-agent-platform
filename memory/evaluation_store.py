"""评估记录持久化：按 student_id 存储为 JSON 文件。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

DEFAULT_MEMORY_DIR = Path(__file__).resolve().parent.parent / "data" / "memory" / "students"
STUDENT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_student_id(student_id: str) -> str:
    """校验并规范化 student_id（用作文件名）。"""
    value = (student_id or "").strip()
    if not value:
        raise ValueError("student_id 不能为空")
    if not STUDENT_ID_PATTERN.match(value):
        raise ValueError(
            "student_id 仅允许字母、数字、下划线、连字符，长度 1～64"
        )
    return value


def get_memory_path(
    student_id: str,
    *,
    memory_dir: Path | None = None,
) -> Path:
    """返回该学生的 memory JSON 文件路径。"""
    safe_id = sanitize_student_id(student_id)
    base = memory_dir or DEFAULT_MEMORY_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{safe_id}.json"


def empty_student_memory(student_id: str) -> dict[str, Any]:
    """构造空的学生记忆结构。"""
    now = _utc_now_iso()
    return {
        "student_id": sanitize_student_id(student_id),
        "created_at": now,
        "updated_at": now,
        "evaluations": [],
        "meta": {"total_evaluations": 0},
    }


def load_student_memory(
    student_id: str,
    *,
    memory_dir: Path | None = None,
    create_if_missing: bool = True,
) -> dict[str, Any]:
    """加载学生长期记忆；不存在时可创建空结构。"""
    path = get_memory_path(student_id, memory_dir=memory_dir)
    if not path.is_file():
        if create_if_missing:
            return empty_student_memory(student_id)
        raise FileNotFoundError(f"学生记忆不存在: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"记忆文件格式无效: {path}")
    data.setdefault("student_id", sanitize_student_id(student_id))
    data.setdefault("evaluations", [])
    data.setdefault("meta", {})
    return data


def save_student_memory(
    student_id: str,
    memory: dict[str, Any],
    *,
    memory_dir: Path | None = None,
) -> Path:
    """原子写入学生记忆 JSON。"""
    path = get_memory_path(student_id, memory_dir=memory_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    memory = dict(memory)
    memory["student_id"] = sanitize_student_id(student_id)
    memory["updated_at"] = _utc_now_iso()
    if "created_at" not in memory:
        memory["created_at"] = memory["updated_at"]

    evaluations = memory.get("evaluations")
    if isinstance(evaluations, list):
        memory.setdefault("meta", {})
        memory["meta"]["total_evaluations"] = len(evaluations)

    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
    return path


def build_evaluation_record(
    *,
    student_input: str,
    routes: list[str] | None = None,
    route: str | None = None,
    route_reason: str | None = None,
    evaluation_mode: str | None = None,
    theory_result: Any = None,
    practice_result: Any = None,
    data_result: Any = None,
    literature_result: Any = None,
    group_project_results: Any = None,
    dimension_summary: Any = None,
    primary_indicator_summary: Any = None,
    dimension_mean_score: Any = None,
    total_score: Any = None,
    score_detail: Any = None,
    final_feedback: str | None = None,
    final_comment: str | None = None,
    audit_passed: bool | None = None,
    audit_status: str | None = None,
    section_results: Any = None,
    section_summary: Any = None,
    section_target: str | None = None,
    history_memory: list[Any] | None = None,
    uploaded_files: list[Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造单条评估记录（含各域结果与综合分数）。"""
    preview_len = 800
    record: dict[str, Any] = {
        "evaluation_id": str(uuid4()),
        "timestamp": _utc_now_iso(),
        "evaluation_mode": evaluation_mode or "route",
        "routes": routes or [],
        "route": route,
        "route_reason": route_reason or "",
        "student_input_preview": (student_input or "")[:preview_len],
        "theory_result": theory_result,
        "practice_result": practice_result,
        "data_result": data_result,
        "literature_result": literature_result,
        "group_project_results": group_project_results,
        "dimension_summary": dimension_summary or [],
        "primary_indicator_summary": primary_indicator_summary or [],
        "dimension_mean_score": dimension_mean_score,
        "total_score": total_score,
        "score_detail": score_detail,
        "final_feedback": final_feedback or "",
        "final_comment": final_comment or "",
        "history_memory": history_memory or [],
        "uploaded_files": uploaded_files or [],
    }
    if audit_passed is not None:
        record["audit_passed"] = audit_passed
    if audit_status:
        record["audit_status"] = audit_status
    if section_results is not None:
        record["section_results"] = section_results
    if section_summary is not None:
        record["section_summary"] = section_summary
    if section_target:
        record["section_target"] = section_target
    if extra:
        record["extra"] = extra
    return record


def append_evaluation(
    student_id: str,
    record: dict[str, Any],
    *,
    memory_dir: Path | None = None,
    max_records: int | None = None,
) -> dict[str, Any]:
    """追加一条评估记录并持久化。"""
    memory = load_student_memory(student_id, memory_dir=memory_dir)
    evaluations: list[dict[str, Any]] = list(memory.get("evaluations") or [])
    evaluations.append(record)
    if max_records is not None and max_records > 0 and len(evaluations) > max_records:
        evaluations = evaluations[-max_records:]
    memory["evaluations"] = evaluations
    save_student_memory(student_id, memory, memory_dir=memory_dir)
    return record


def list_evaluations(
    student_id: str,
    *,
    memory_dir: Path | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """按时间顺序返回评估记录（最新在末尾）。"""
    memory = load_student_memory(
        student_id, memory_dir=memory_dir, create_if_missing=False
    )
    items: list[dict[str, Any]] = list(memory.get("evaluations") or [])
    if offset:
        items = items[offset:]
    if limit is not None and limit >= 0:
        items = items[-limit:] if limit else []
    return items


def get_evaluation_by_id(
    student_id: str,
    evaluation_id: str,
    *,
    memory_dir: Path | None = None,
) -> dict[str, Any] | None:
    for item in list_evaluations(student_id, memory_dir=memory_dir):
        if item.get("evaluation_id") == evaluation_id:
            return item
    return None


def delete_student_memory(
    student_id: str,
    *,
    memory_dir: Path | None = None,
) -> bool:
    """删除学生记忆文件。"""
    path = get_memory_path(student_id, memory_dir=memory_dir)
    if path.is_file():
        path.unlink()
        return True
    return False


__all__ = [
    "DEFAULT_MEMORY_DIR",
    "append_evaluation",
    "build_evaluation_record",
    "delete_student_memory",
    "empty_student_memory",
    "get_evaluation_by_id",
    "get_memory_path",
    "list_evaluations",
    "load_student_memory",
    "save_student_memory",
    "sanitize_student_id",
]
