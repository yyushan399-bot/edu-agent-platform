"""作业提交 API：保存自评并触发 LangGraph 评估。"""

from __future__ import annotations

import logging
import traceback
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from api.common import (
    build_student_input_from_files,
    clamp_score,
    first_file_url,
    save_upload_file,
)
from api.graph_service import run_langgraph_analysis
from database import Assignment, Evaluation, SelfAssessment, User, get_db
from llm_config import is_dotenv_loaded

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assignments", tags=["assignments"])


def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"用户不存在: user_id={user_id}")
    return user


def _get_assignment_or_404(db: Session, assignment_id: int) -> Assignment:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(
            status_code=404,
            detail=f"作业不存在: assignment_id={assignment_id}",
        )
    return assignment


def upsert_self_assessment(
    db: Session,
    *,
    user_id: int,
    assignment_id: int,
    score: float,
    comment: str | None,
) -> SelfAssessment:
    """保存或更新学生自评（每用户每作业唯一）。"""
    record = (
        db.query(SelfAssessment)
        .filter_by(user_id=user_id, assignment_id=assignment_id)
        .one_or_none()
    )
    if record is None:
        record = SelfAssessment(
            user_id=user_id,
            assignment_id=assignment_id,
            score=score,
            comment=comment,
        )
        db.add(record)
    else:
        record.score = score
        record.comment = comment
    db.flush()
    return record


def save_evaluation(
    db: Session,
    *,
    user_id: int,
    assignment_id: int,
    graph_result: dict[str, Any],
    file_url: str | None = None,
) -> Evaluation:
    """将 LangGraph 结果写入 evaluations 表。"""
    routes = graph_result.get("routes") or []
    route = routes[0] if routes else graph_result.get("route")
    evaluation = Evaluation(
        user_id=user_id,
        assignment_id=assignment_id,
        route=str(route) if route else None,
        total_score=graph_result.get("total_score"),
        final_feedback=graph_result.get("final_feedback"),
        file_url=file_url,
    )
    db.add(evaluation)
    db.flush()
    return evaluation


def _self_assessment_payload(record: SelfAssessment) -> dict[str, Any]:
    return {
        "id": record.id,
        "user_id": record.user_id,
        "assignment_id": record.assignment_id,
        "score": record.score,
        "comment": record.comment,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@router.post("/{assignment_id}/submit")
async def submit_assignment(
    assignment_id: int,
    user_id: Annotated[int, Form(description="提交用户 ID（users.id）")],
    self_score: Annotated[float, Form(description="自评分数 0-100")],
    self_comment: Annotated[str | None, Form(description="自评说明（可选）")] = None,
    files: Annotated[
        list[UploadFile],
        File(description="PDF / DOCX / PNG / JPG / JPEG"),
    ] = [],
    text: Annotated[str | None, Form(description="补充文本（可选）")] = None,
    student_id: Annotated[
        str | None,
        Form(description="学生 ID 字符串（可选，长期记忆 student_id）"),
    ] = None,
    routes: Annotated[
        str | None,
        Form(description="预设路由，逗号分隔，如 theory,data"),
    ] = None,
    memory_k: Annotated[int, Form(description="历史记忆条数")] = 3,
    enable_deep_research: Annotated[
        bool,
        Form(description="是否启用 Deep Research（默认关闭）"),
    ] = False,
    session_id: Annotated[
        str | None,
        Form(description="会话 ID（可选，用于多轮对话）"),
    ] = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    提交作业：保存自评 → LangGraph AI 评估 → 写入 evaluations。

    - self_score / self_comment → self_assessments 表
    - AI 评估结果 → evaluations 表
    """
    _get_user_or_404(db, user_id)
    _get_assignment_or_404(db, assignment_id)

    score = clamp_score(self_score)
    comment = (self_comment or "").strip() or None

    saved_meta: list[dict[str, str]] = []
    saved_paths: list[str] = []

    for upload in files:
        meta = await save_upload_file(upload)
        saved_meta.append(meta)
        saved_paths.append(meta["path"])

    if not saved_paths and not (text or "").strip():
        raise HTTPException(status_code=400, detail="请至少上传一个文件或填写文本")

    if not is_dotenv_loaded():
        raise HTTPException(
            status_code=400,
            detail="未配置 OPENAI_API_KEY，请在项目根目录 .env 中设置后重启后端",
        )

    extra = (text or "").strip() or None
    try:
        student_input, uploaded_files = build_student_input_from_files(
            saved_paths,
            extra_text=extra,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"文件解析失败: {exc}") from exc

    route_list: list[str] | None = None
    if routes:
        from state import normalize_routes

        route_list = normalize_routes(
            [r.strip() for r in routes.split(",") if r.strip()]
        )

    memory_student_id = (student_id or "").strip() or str(user_id)

    try:
        graph_result = run_langgraph_analysis(
            student_input,
            uploaded_files=uploaded_files,
            routes=route_list,
            student_id=memory_student_id,
            session_id=(session_id or "").strip() or None,
            memory_retrieve_k=memory_k,
            enable_deep_research=enable_deep_research,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("LangGraph failed:\n%s", traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"LangGraph 执行失败: {type(exc).__name__}: {exc}",
        ) from exc

    try:
        self_record = upsert_self_assessment(
            db,
            user_id=user_id,
            assignment_id=assignment_id,
            score=score,
            comment=comment,
        )
        evaluation = save_evaluation(
            db,
            user_id=user_id,
            assignment_id=assignment_id,
            graph_result=graph_result,
            file_url=first_file_url(saved_meta),
        )
        db.commit()
        db.refresh(self_record)
        db.refresh(evaluation)
    except Exception as exc:
        db.rollback()
        logger.error("Database save failed:\n%s", traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"保存自评或评估记录失败: {exc}",
        ) from exc

    active_session_id = (session_id or "").strip()
    if active_session_id:
        try:
            from memory.session_manager import SessionManager, load_session, save_session

            session_mgr = SessionManager(active_session_id)
            user_parts: list[str] = []
            if saved_meta:
                names = ", ".join(item.get("name", "文件") for item in saved_meta)
                user_parts.append(f"📎 {names}")
            if (text or "").strip():
                user_parts.append((text or "").strip())
            if not user_parts:
                user_parts.append("（提交了作业内容）")
            if comment:
                user_parts.append(f"自评 {score} 分：{comment}")
            user_content = "\n".join(user_parts)
            session_data = load_session(active_session_id)
            meta = dict(session_data.get("meta") or {})
            if meta.get("title") in (None, "", "新会话") and user_content:
                meta["title"] = user_content[:32] + (
                    "…" if len(user_content) > 32 else ""
                )
                session_data["meta"] = meta
                save_session(session_data)
            session_mgr.save_message(
                "user",
                user_content,
                meta={
                    "files": saved_meta,
                    "routes": route_list,
                    "assignment_id": assignment_id,
                    "self_score": score,
                },
            )
            feedback = str(graph_result.get("final_feedback") or "").strip()
            if feedback:
                session_mgr.save_message(
                    "assistant",
                    feedback,
                    meta={
                        "routes": graph_result.get("routes"),
                        "route_reason": graph_result.get("route_reason"),
                        "total_score": graph_result.get("total_score"),
                        "score_detail": graph_result.get("score_detail"),
                        "evaluation_id": evaluation.id,
                    },
                )
        except Exception as exc:
            logger.warning("会话消息保存失败 session_id=%s: %s", active_session_id, exc)

    return jsonable_encoder(
        {
            "success": True,
            "assignment_id": assignment_id,
            "user_id": user_id,
            "self_assessment": _self_assessment_payload(self_record),
            "evaluation_id": evaluation.id,
            "session_id": active_session_id or None,
            "saved_files": saved_meta,
            "student_input_preview": student_input[:500],
            "routes": graph_result.get("routes"),
            "route_reason": graph_result.get("route_reason"),
            "final_feedback": graph_result.get("final_feedback"),
            "total_score": graph_result.get("total_score"),
            "score_detail": graph_result.get("score_detail"),
            "theory_result": graph_result.get("theory_result"),
            "practice_result": graph_result.get("practice_result"),
            "data_result": graph_result.get("data_result"),
            "literature_result": graph_result.get("literature_result"),
            "last_saved_evaluation_id": graph_result.get("last_saved_evaluation_id"),
        }
    )


__all__ = ["router", "submit_assignment", "upsert_self_assessment"]
