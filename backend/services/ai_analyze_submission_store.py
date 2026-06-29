"""AI 作业分析（/analyze）提交持久化。"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from backend.models import AiAnalyzeSubmission, User

_SELF_SCORE_RE = re.compile(r"【自评\s*([\d.]+)\s*/\s*5\s*分】", re.I)


def _extract_self_comment(text: str | None) -> tuple[float | None, str | None]:
    raw = (text or "").strip()
    if not raw:
        return None, None
    score: float | None = None
    m = _SELF_SCORE_RE.search(raw)
    if m:
        try:
            score = round(float(m.group(1)), 1)
        except (TypeError, ValueError):
            score = None
    lines = raw.splitlines()
    comment_lines: list[str] = []
    for line in lines:
        if _SELF_SCORE_RE.search(line):
            continue
        comment_lines.append(line)
    comment = "\n".join(comment_lines).strip() or None
    return score, comment


def save_ai_analyze_submission(
    db: Session,
    *,
    student_id: str,
    project_id: int,
    session_id: str | None,
    saved_meta: list[dict[str, str]],
    extra_text: str | None,
    self_score: float | None,
    routes: list[str] | None,
    graph_result: dict[str, Any],
) -> AiAnalyzeSubmission | None:
    """将一次 /analyze 成功结果写入数据库，供同组互评列表使用。"""
    sid = (student_id or "").strip()
    if not sid or not project_id:
        return None

    user = db.query(User).filter(User.student_id == sid).first()
    if user is None:
        return None

    first = saved_meta[0] if saved_meta else {}
    filename = first.get("name") or "作业文件"
    file_path = first.get("path") or None

    parsed_self, self_comment = _extract_self_comment(extra_text)
    final_self = self_score if self_score is not None else parsed_self

    feedback = str(graph_result.get("final_feedback") or "").strip()
    record = AiAnalyzeSubmission(
        user_id=user.id,
        student_id=sid,
        project_id=project_id,
        session_id=(session_id or "").strip() or None,
        filename=filename,
        file_path=file_path,
        self_score=final_self,
        self_comment=self_comment,
        routes=list(routes) if routes else None,
        ai_total_score=_to_float(graph_result.get("total_score")),
        feedback_preview=feedback[:500] if feedback else None,
    )
    db.add(record)
    db.flush()
    return record


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
