"""FastAPI 后端：多模态上传 + LangGraph 分析。"""

from __future__ import annotations

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

from api.assignments import router as assignments_router  # noqa: E402
from api.common import UPLOAD_DIR, build_student_input_from_files, save_upload_file  # noqa: E402
from api.graph_service import run_langgraph_analysis  # noqa: E402
from api.peer_review import router as peer_review_router  # noqa: E402
from llm_config import is_dotenv_loaded  # noqa: E402

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

app.include_router(assignments_router)
app.include_router(peer_review_router)
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
async def list_sessions_api(limit: int = 100) -> dict[str, Any]:
    from memory.session_manager import list_sessions

    sessions = list_sessions(limit=max(1, min(limit, 200)))
    return {"success": True, "sessions": sessions}


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
async def health() -> dict[str, str | bool]:
    from deep_research.config import is_deep_research_enabled
    from rag.rag_config import is_rag_enabled

    return {
        "status": "ok",
        "llm_configured": is_dotenv_loaded(),
        "rag_enabled": is_rag_enabled(),
        "deep_research_available": is_deep_research_enabled(),
    }


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
                meta={"files": saved_meta, "routes": route_list},
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
                    },
                )
        except Exception as exc:
            logger.warning("会话消息保存失败 session_id=%s: %s", active_session_id, exc)

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
