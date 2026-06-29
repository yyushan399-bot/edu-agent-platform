"""FastAPI 后端：多模态上传 + LangGraph 分析。"""

from __future__ import annotations

import asyncio
import logging
import sys
import traceback
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# 保证可导入项目根目录模块（input、main_graph 等）
_API_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _API_DIR.parent
PROJECT_ROOT = _BACKEND_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from pydantic import BaseModel

from api.common import UPLOAD_DIR, build_student_input_from_files, save_upload_file  # noqa: E402
from api.graph_service import run_langgraph_analysis  # noqa: E402
from llm_config import is_dotenv_loaded  # noqa: E402

try:
    import os as _os

    if _os.environ.get("EDU_SKIP_LEGACY_ROUTERS") != "1":
        from api.assignments import router as assignments_router  # noqa: E402
    else:
        assignments_router = None
except Exception as exc:
    assignments_router = None
    logger.warning("作业 assignments 路由未加载（可忽略）: %s", exc)

try:
    if _os.environ.get("EDU_SKIP_LEGACY_ROUTERS") != "1":
        from api.peer_review import router as peer_review_router  # noqa: E402
    else:
        peer_review_router = None
except Exception as exc:
    peer_review_router = None
    logger.warning("互评 peer_review 路由未加载（可忽略）: %s", exc)

try:
    if _os.environ.get("EDU_SKIP_LEGACY_ROUTERS") != "1":
        from api.summative_evaluation import router as summative_router  # noqa: E402
    else:
        summative_router = None
except Exception as exc:
    summative_router = None
    logger.warning("终结性评价 summative 路由未加载（可忽略）: %s", exc)

app = FastAPI(
    title="教育智能体 API",
    description="上传 PDF / Word / 图片，调用 LangGraph 进行评估",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

if assignments_router:
    app.include_router(assignments_router)
if peer_review_router:
    app.include_router(peer_review_router)
if summative_router:
    app.include_router(summative_router)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


class CreateSessionRequest(BaseModel):
    student_id: str | None = None
    title: str | None = "新会话"


def _session_summary(session: dict[str, Any]) -> dict[str, Any]:
    from memory.session_manager import _derive_session_title

    messages = list(session.get("messages") or [])
    meta = dict(session.get("meta") or {})
    title = str(meta.get("title") or "").strip() or _derive_session_title(messages)
    last = messages[-1] if messages else {}
    return {
        "session_id": session.get("session_id"),
        "title": title,
        "student_id": session.get("student_id") or "",
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "message_count": len(messages),
        "preview": str(last.get("content") or "")[:80],
    }


@app.get("/sessions")
async def list_sessions_api(
    limit: int = 100,
    student_id: str | None = None,
) -> dict[str, Any]:
    from memory.session_manager import list_sessions

    sessions = list_sessions(limit=max(1, min(limit, 200)))
    sid = (student_id or "").strip()
    if sid:
        sessions = [s for s in sessions if str(s.get("student_id") or "") == sid]
    return {"success": True, "sessions": sessions}


@app.get("/sessions/by-student/{student_id}/messages")
async def student_messages_api(
    student_id: str,
    limit: int = 300,
) -> dict[str, Any]:
    """按学号聚合该学生所有 AI 会话消息（教师端查看）。"""
    from backend.services.chat_history import get_student_chat_messages

    sid = (student_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="student_id 不能为空")

    try:
        data = get_student_chat_messages(sid, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"success": True, **data}


@app.post("/sessions")
async def create_session_api(body: CreateSessionRequest) -> dict[str, Any]:
    from memory.session_manager import SessionManager

    meta: dict[str, Any] = {"title": (body.title or "新会话").strip() or "新会话"}
    manager = SessionManager.create_session(
        student_id=(body.student_id or "").strip() or None,
        meta=meta,
    )
    session = manager.load()
    return {"success": True, "session": _session_summary(session)}


@app.get("/sessions/{session_id}")
async def get_session_api(session_id: str) -> dict[str, Any]:
    from memory.session_manager import SessionManager

    try:
        manager = SessionManager(session_id)
        session = manager.load()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc

    return {
        "success": True,
        "session": _session_summary(session),
        "messages": manager.load_history(),
    }


@app.get("/health")
async def health() -> dict[str, str | bool | list[str] | None]:
    from api.graph_service import SUPPORTED_EVALUATION_MODES
    from deep_research.config import is_deep_research_enabled
    from rag.rag_config import is_rag_enabled

    graphrag: dict[str, Any] = {
        "graphrag_available": False,
        "graphrag_backend": None,
        "graphrag_configured": False,
    }
    try:
        from services.section_graphrag_service import probe_graphrag_health

        graphrag = probe_graphrag_health()
    except Exception as exc:
        logger.debug("GraphRAG 健康检查跳过: %s", exc)

    return {
        "status": "ok",
        "llm_configured": is_dotenv_loaded(),
        "rag_enabled": is_rag_enabled(),
        "deep_research_available": is_deep_research_enabled(),
        "evaluation_modes": list(SUPPORTED_EVALUATION_MODES),
        "pbl_endpoint": "/group-evaluation",
        "route_endpoint": "/analyze",
        "section_endpoint": "/section-evaluation",
        "summative_endpoint": "/summative-evaluation",
        "graphrag_available": graphrag["graphrag_available"],
        "graphrag_backend": graphrag.get("graphrag_backend"),
        "graphrag_configured": graphrag.get("graphrag_configured"),
        "section_graphrag_endpoint": "/section-graphrag/context",
    }


@app.get("/section-graphrag/health")
async def section_graphrag_health() -> dict[str, Any]:
    from services.section_graphrag_service import probe_graphrag_health

    graphrag = probe_graphrag_health()
    return {"success": True, **graphrag}


@app.get("/section-graphrag/context")
async def section_graphrag_context(section_name: str) -> dict[str, Any]:
    """返回指定章节的 GraphRAG 指标、权重与量规（阶段 2 验收入口）。"""
    from utils.section_constants import SECTION_NAMES
    from services.section_graphrag_service import create_section_retriever, probe_graphrag_health

    if section_name not in SECTION_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"未知章节：{section_name}。可选：{', '.join(SECTION_NAMES)}",
        )

    graphrag = probe_graphrag_health()
    if not graphrag["graphrag_available"]:
        raise HTTPException(
            status_code=503,
            detail=graphrag.get("graphrag_error") or "GraphRAG 不可用",
        )

    retriever = create_section_retriever()
    try:
        context = retriever.retrieve_full_context(section_name)
    finally:
        retriever.close()

    return {
        "success": True,
        "section_name": section_name,
        "backend": retriever.backend_name,
        "criteria_count": len(context.get("criteria", [])),
        "context": context,
    }


@app.post("/group-evaluation")
async def group_evaluation(
    file: Annotated[UploadFile, File(description="PDF / DOCX / TXT 项目报告")],
    enable_review: Annotated[
        bool,
        Form(description="是否启用完整 PBL 流程（审核 + 12 维 + 一级汇总，较慢）"),
    ] = True,
    review_rounds: Annotated[int, Form(description="审核最大重评轮数")] = 5,
    scoring_times: Annotated[
        int,
        Form(description="每维度独立评分次数（默认 10，可通过 PBL_SCORING_TIMES 配置）"),
    ] | None = None,
    rag_top_k: Annotated[int, Form(description="每维度 RAG 检索数量")] | None = None,
    student_id: Annotated[
        str | None,
        Form(description="学生 ID（可选，写入长期记忆 JSON）"),
    ] = None,
    session_id: Annotated[
        str | None,
        Form(description="会话 ID（可选，用于多轮对话记录）"),
    ] = None,
    project_id: Annotated[
        int | None,
        Form(description="当前项目 ID（用于截止+30 天可见性规则）"),
    ] = None,
) -> dict[str, Any]:
    """
    上传小组项目报告，经 PBL 主图评价（记忆检索 → 评分 → 持久化）。

    enable_review=false：快速模式（三 agent 串行评分）
    enable_review=true：完整 PBL 模式（并行审核 + 一级汇总）

    分数尺度为 1.0–5.0（evaluation_mode=pbl_report）。
    """
    from api.graph_service import run_pbl_analysis
    from agents.group_project.pbl_config import DEFAULT_RAG_TOP_K, DEFAULT_SCORING_TIMES
    from utils.file_parser import SUPPORTED_SUFFIXES, extract_text_from_file

    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        allowed = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {suffix or '(无扩展名)'}，允许: {allowed}",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="上传文件为空")

    try:
        report_text = extract_text_from_file(file_bytes, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("group evaluation file parse failed: %s", filename)
        raise HTTPException(
            status_code=400,
            detail=f"文件解析失败: {type(exc).__name__}: {exc}",
        ) from exc

    if not is_dotenv_loaded():
        raise HTTPException(
            status_code=400,
            detail="未配置 OPENAI_API_KEY，请在项目根目录 .env 中设置后重启后端",
        )

    logger.info(
        "group evaluation request (filename=%s, text_len=%d, enable_review=%s, "
        "review_rounds=%d, student_id=%s)",
        filename,
        len(report_text),
        enable_review,
        review_rounds,
        (student_id or "").strip() or "(none)",
    )

    try:
        evaluation = await asyncio.to_thread(
            run_pbl_analysis,
            report_text,
            student_id=(student_id or "").strip() or None,
            session_id=(session_id or "").strip() or None,
            enable_pbl_review=enable_review,
            pbl_scoring_times=scoring_times if scoring_times is not None else DEFAULT_SCORING_TIMES,
            pbl_rag_top_k=rag_top_k if rag_top_k is not None else DEFAULT_RAG_TOP_K,
            pbl_review_rounds=max(0, review_rounds),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("group evaluation failed:\n%s", traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"小组项目评估失败: {type(exc).__name__}: {exc}",
        ) from exc

    active_session_id = (session_id or "").strip()
    if not active_session_id:
        try:
            from backend.services.chat_history import resolve_or_create_session_id

            active_session_id = resolve_or_create_session_id(
                session_id,
                student_id,
                title=f"小组项目 · {filename[:24]}",
            )
        except Exception as exc:
            logger.warning("PBL 自动创建会话失败: %s", exc)

    if active_session_id:
        try:
            from backend.services.chat_history import append_session_exchange

            append_session_exchange(
                active_session_id,
                student_id=(student_id or "").strip() or None,
                user_content=f"📎 {filename}\n（小组项目评价）",
                user_meta={"filename": filename, "evaluation_mode": "pbl_report"},
                assistant_content=str(
                    evaluation.get("final_comment") or evaluation.get("final_feedback") or ""
                ).strip()
                or None,
                assistant_meta={
                    "evaluation_mode": "pbl_report",
                    "final_score": evaluation.get("final_score"),
                    "dimension_mean_score": evaluation.get("dimension_mean_score"),
                    "audit_passed": evaluation.get("audit_passed"),
                },
            )
        except Exception as exc:
            logger.warning(
                "PBL 会话消息保存失败 session_id=%s: %s",
                active_session_id,
                exc,
            )

    response_payload: dict[str, Any] = {
        "success": True,
        "filename": filename,
        "text_length": len(report_text),
        "text_preview": report_text[:500],
        "enable_review": enable_review,
        "student_id": (student_id or "").strip() or None,
        "session_id": active_session_id or None,
        **evaluation,
    }

    sid = (student_id or "").strip()
    if sid:
        try:
            from backend.database import SessionLocal
            from backend.models import User, UserRole
            from backend.services.group_pbl_store import (
                save_group_pbl_evaluation,
                save_group_pbl_upload_file,
            )
            from backend.services.pbl_visibility import can_leader_view_scores, mask_leader_scores

            db = SessionLocal()
            try:
                user = db.query(User).filter(User.student_id == sid).first()
                user_id = user.id if user else 0
                stored_file_path = save_group_pbl_upload_file(
                    file_bytes=file_bytes,
                    filename=filename,
                    student_id=sid,
                )
                save_group_pbl_evaluation(
                    db,
                    student_id=sid,
                    user_id=user_id,
                    filename=filename,
                    report_text=report_text,
                    evaluation=dict(evaluation),
                    project_id=project_id,
                    file_path=stored_file_path,
                )
                if user and user.role == UserRole.group_leader:
                    visible, visible_at = can_leader_view_scores(db, user, project_id)
                    response_payload = mask_leader_scores(
                        response_payload,
                        visible=visible,
                        visible_at=visible_at,
                    )
            finally:
                db.close()
        except Exception as exc:
            logger.warning("PBL 结果持久化/可见性处理失败: %s", exc)

    return jsonable_encoder(response_payload)


@app.post("/section-evaluation")
async def section_evaluation(
    file: Annotated[
        UploadFile | None,
        File(description="PDF / DOCX / TXT 项目报告（与 text 二选一）"),
    ] = None,
    text: Annotated[
        str | None,
        Form(description="报告正文或单章文本（可选）"),
    ] = None,
    section_name: Annotated[
        str | None,
        Form(description="指定评价单章；留空则评价切分出的全部章节"),
    ] = None,
    enable_review: Annotated[
        bool,
        Form(description="是否启用章节审核循环（较慢）"),
    ] = True,
    review_rounds: Annotated[int, Form(description="审核最大重评轮数")] = 3,
    scoring_times: Annotated[
        int,
        Form(description="每指标独立评分次数"),
    ] | None = None,
    cv_threshold: Annotated[
        float,
        Form(description="CV 稳定性阈值"),
    ] | None = None,
    student_id: Annotated[
        str | None,
        Form(description="学生 ID（可选，写入长期记忆 JSON）"),
    ] = None,
    session_id: Annotated[
        str | None,
        Form(description="会话 ID（可选）"),
    ] = None,
) -> dict[str, Any]:
    """
    上传项目报告或提交文本，经章节反馈主图评价（记忆 → 切分 → 评分 → 汇总）。

    分数尺度为 1.0–5.0（evaluation_mode=section_report）。
    """
    from api.graph_service import run_section_analysis
    from agents.group_project.pbl_config import DEFAULT_SCORING_TIMES
    from agents.section_report.section_config import (
        DEFAULT_CV_THRESHOLD,
        DEFAULT_MAX_REVIEW_ROUNDS,
        SECTION_NAMES,
    )
    from utils.file_parser import SUPPORTED_SUFFIXES, extract_text_from_file

    active_section = (section_name or "").strip()
    if active_section and active_section not in SECTION_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"未知章节：{active_section}。可选：{', '.join(SECTION_NAMES)}",
        )

    report_text = (text or "").strip()
    section_texts: dict[str, str] | None = None
    filename = "text-input"

    if file is not None and file.filename:
        filename = file.filename
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            allowed = ", ".join(sorted(SUPPORTED_SUFFIXES))
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型: {suffix or '(无扩展名)'}，允许: {allowed}",
            )
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="上传文件为空")
        try:
            report_text = extract_text_from_file(file_bytes, filename)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("section evaluation file parse failed: %s", filename)
            raise HTTPException(
                status_code=400,
                detail=f"文件解析失败: {type(exc).__name__}: {exc}",
            ) from exc
    elif active_section and report_text:
        section_texts = {active_section: report_text}
        report_text = report_text
    elif not report_text:
        raise HTTPException(status_code=400, detail="请上传文件或填写 text")

    if not is_dotenv_loaded():
        raise HTTPException(
            status_code=400,
            detail="未配置 OPENAI_API_KEY，请在项目根目录 .env 中设置后重启后端",
        )

    logger.info(
        "section evaluation request (filename=%s, text_len=%d, section=%s, review=%s, student_id=%s)",
        filename,
        len(report_text),
        active_section or "ALL",
        enable_review,
        (student_id or "").strip() or "(none)",
    )

    try:
        evaluation = await asyncio.to_thread(
            run_section_analysis,
            report_text,
            section_name=active_section or None,
            section_texts=section_texts,
            student_id=(student_id or "").strip() or None,
            session_id=(session_id or "").strip() or None,
            enable_section_review=enable_review,
            section_scoring_times=scoring_times if scoring_times is not None else DEFAULT_SCORING_TIMES,
            section_review_rounds=max(1, review_rounds or DEFAULT_MAX_REVIEW_ROUNDS),
            section_cv_threshold=cv_threshold if cv_threshold is not None else DEFAULT_CV_THRESHOLD,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("section evaluation failed:\n%s", traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"章节反馈评估失败: {type(exc).__name__}: {exc}",
        ) from exc

    active_session_id = (session_id or "").strip()
    if not active_session_id:
        try:
            from backend.services.chat_history import resolve_or_create_session_id

            active_session_id = resolve_or_create_session_id(
                session_id,
                student_id,
                title=f"章节反馈 · {filename[:24]}",
            )
        except Exception as exc:
            logger.warning("章节反馈自动创建会话失败: %s", exc)

    if active_session_id:
        try:
            from backend.services.chat_history import append_session_exchange

            append_session_exchange(
                active_session_id,
                student_id=(student_id or "").strip() or None,
                user_content=f"📎 {filename}\n（章节反馈 · {active_section or '全部章节'}）",
                user_meta={
                    "filename": filename,
                    "evaluation_mode": "section_report",
                    "section_name": active_section or None,
                },
                assistant_content=str(
                    evaluation.get("final_comment") or evaluation.get("final_feedback") or ""
                ).strip()
                or None,
                assistant_meta={
                    "evaluation_mode": "section_report",
                    "overall_score": evaluation.get("overall_score"),
                    "section_scores": evaluation.get("section_scores"),
                },
            )
        except Exception as exc:
            logger.warning(
                "章节反馈会话消息保存失败 session_id=%s: %s",
                active_session_id,
                exc,
            )

    return jsonable_encoder(
        {
            "success": True,
            "filename": filename,
            "text_length": len(report_text),
            "text_preview": report_text[:500],
            "enable_review": enable_review,
            "section_name": active_section or None,
            "student_id": (student_id or "").strip() or None,
            "session_id": active_session_id or None,
            **evaluation,
        }
    )


@app.post("/analyze")
async def analyze(
    files: Annotated[list[UploadFile], File(description="PDF / DOCX / PNG / JPG / JPEG")] = [],
    text: Annotated[str | None, Form(description="补充文本（可选）")] = None,
    student_id: Annotated[str | None, Form(description="学生 ID（可选，长期记忆）")] = None,
    routes: Annotated[
        str | None,
        Form(description="预设路由，逗号分隔，如 theory,data"),
    ] = None,
    memory_k: Annotated[int, Form(description="历史记忆条数")] = 3,
    enable_deep_research: Annotated[
        bool,
        Form(description="是否启用 Deep Research（默认关闭，较慢）"),
    ] = False,
    session_id: Annotated[
        str | None,
        Form(description="会话 ID（可选，用于多轮对话）"),
    ] = None,
    self_score: Annotated[
        float | None,
        Form(description="学生自评分数 0-5"),
    ] = None,
    project_id: Annotated[
        int | None,
        Form(description="当前项目 ID（互评同组可见）"),
    ] = None,
) -> dict[str, Any]:
    """
    上传作业文件并触发 LangGraph 分析（不含数据库自评）。

    若需保存 self_score / self_comment，请使用 POST /assignments/{id}/submit。
    """
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
        raise HTTPException(
            status_code=400,
            detail=f"文件解析失败: {exc}",
        ) from exc

    route_list: list[str] | None = None
    if routes:
        from state import normalize_routes

        route_list = normalize_routes(
            [r.strip() for r in routes.split(",") if r.strip()]
        )

    try:
        graph_result = run_langgraph_analysis(
            student_input,
            uploaded_files=uploaded_files,
            routes=route_list,
            student_id=(student_id or "").strip() or None,
            session_id=(session_id or "").strip() or None,
            memory_retrieve_k=memory_k,
            enable_deep_research=enable_deep_research,
            self_score=self_score,
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

    active_session_id = (session_id or "").strip()
    if not active_session_id:
        try:
            from backend.services.chat_history import resolve_or_create_session_id

            active_session_id = resolve_or_create_session_id(
                session_id,
                student_id,
                title="AI 形成性评价",
            )
        except Exception as exc:
            logger.warning("analyze 自动创建会话失败: %s", exc)

    if active_session_id:
        try:
            from backend.services.chat_history import append_session_exchange

            user_parts: list[str] = []
            if saved_meta:
                names = ", ".join(item.get("name", "文件") for item in saved_meta)
                user_parts.append(f"📎 {names}")
            if (text or "").strip():
                user_parts.append((text or "").strip())
            if not user_parts:
                user_parts.append("（提交了作业内容）")
            user_content = "\n".join(user_parts)
            append_session_exchange(
                active_session_id,
                student_id=(student_id or "").strip() or None,
                user_content=user_content,
                user_meta={"files": saved_meta, "routes": route_list},
                assistant_content=str(graph_result.get("final_feedback") or "").strip() or None,
                assistant_meta={
                    "evaluation_mode": "route",
                    "evaluation_stage": "formative",
                    "routes": graph_result.get("routes"),
                    "route_reason": graph_result.get("route_reason"),
                    "total_score": graph_result.get("total_score"),
                    "self_score": graph_result.get("self_score"),
                    "rubric_score": (graph_result.get("score_detail") or {}).get(
                        "rubric_average"
                    ),
                    "score_detail": graph_result.get("score_detail"),
                },
            )
        except Exception as exc:
            logger.warning("会话消息保存失败 session_id=%s: %s", active_session_id, exc)

    if project_id is not None and project_id > 0:
        try:
            from backend.database import SessionLocal
            from backend.services.ai_analyze_submission_store import save_ai_analyze_submission

            db = SessionLocal()
            try:
                save_ai_analyze_submission(
                    db,
                    student_id=(student_id or "").strip(),
                    project_id=project_id,
                    session_id=active_session_id or None,
                    saved_meta=saved_meta,
                    extra_text=(text or "").strip() or None,
                    self_score=self_score,
                    routes=route_list,
                    graph_result=graph_result,
                )
                db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.warning("AI 作业分析互评记录保存失败: %s", exc)

    return jsonable_encoder(
        {
            "success": True,
            "session_id": active_session_id or None,
            "saved_files": saved_meta,
            "student_input_preview": student_input[:500],
            "routes": graph_result.get("routes"),
            "route_reason": graph_result.get("route_reason"),
            "final_feedback": graph_result.get("final_feedback"),
            "total_score": graph_result.get("total_score"),
            "rubric_score": (graph_result.get("score_detail") or {}).get("rubric_average"),
            "self_score": graph_result.get("self_score"),
            "score_scale": "1-5",
            "score_detail": graph_result.get("score_detail"),
            "theory_result": graph_result.get("theory_result"),
            "practice_result": graph_result.get("practice_result"),
            "data_result": graph_result.get("data_result"),
            "literature_result": graph_result.get("literature_result"),
            "research_context": graph_result.get("research_context"),
            "memory_context": graph_result.get("memory_context"),
            "last_saved_evaluation_id": graph_result.get("last_saved_evaluation_id"),
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        app_dir=str(_BACKEND_DIR),
    )
