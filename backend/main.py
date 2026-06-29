"""FastAPI 应用入口."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.database import engine, Base
from llm_config import is_dotenv_loaded
from backend.migrate import run_lightweight_migrations
from backend.routers import (
    auth_router,
    users_router,
    projects_router,
    groups_router,
    submissions_router,
    evaluations_router,
    teacher_chat_router,
    group_pbl_router,
    teacher_intervention_router,
    peer_review_router,
    ai_analyze_router,
)
from backend.edu_integration import integrate_edu_app

# ── 创建数据库表 ──────────────────────────────────────

Base.metadata.create_all(bind=engine)
run_lightweight_migrations()

# ── 应用 ──────────────────────────────────────────────

app = FastAPI(
    title="项目化学习系统 API",
    description="教育智能体多维度混合评价系统",
    version="1.0.0",
)

# ── CORS ──────────────────────────────────────────────

origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册路由 ──────────────────────────────────────────

app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(projects_router.router)
app.include_router(groups_router.router)
app.include_router(submissions_router.router)
app.include_router(evaluations_router.router)
app.include_router(teacher_chat_router.router)
app.include_router(group_pbl_router.router)
app.include_router(teacher_intervention_router.router)
app.include_router(peer_review_router.router)
app.include_router(ai_analyze_router.router)

# LangGraph AI（原独立 8000 端口）合并到同一进程
_edu_loaded = integrate_edu_app(app)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "项目化学习系统",
        "version": "1.0.0",
        "edu_agent": _edu_loaded,
    }


# ── 生产环境：挂载前端静态文件（支持 SPA 路由） ────
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    from fastapi.responses import FileResponse

    for f in ["favicon.ico", "vite.svg"]:
        p = FRONTEND_DIST / f
        if p.exists():
            p.unlink()

    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/api/edu-health")
    def edu_health():
        return {
            "status": "ok",
            "llm_configured": is_dotenv_loaded(),
            "rag_enabled": True,
            "deep_research_available": True,
            "evaluation_modes": ["analyze", "group_evaluation", "section_evaluation"],
        }

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith(("api/", "uploads/", "assets/")):
            return {"detail": "Not Found"}
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(str(index), media_type="text/html")
        return {"detail": "Not Found"}
