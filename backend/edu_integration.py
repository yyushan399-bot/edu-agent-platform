"""将 LangGraph 教育智能体（原 8000 端口）挂载到主应用。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.routing import Mount

logger = logging.getLogger(__name__)

_BOOTSTRAPPED = False


def bootstrap_edu_paths() -> None:
    """确保可 import input、main_graph、api 等模块。"""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    backend_dir = Path(__file__).resolve().parent
    project_root = backend_dir.parent
    for path in (str(project_root), str(backend_dir)):
        if path not in sys.path:
            sys.path.insert(0, path)
    _BOOTSTRAPPED = True


def _route_signature(route) -> tuple | None:
    """路由唯一键：同一路径的不同 HTTP 方法需分别注册（如 GET/POST /sessions）。"""
    path = getattr(route, "path", None)
    if not path:
        return None
    methods = getattr(route, "methods", None)
    if methods is None:
        return (path, None)
    return (path, frozenset(methods))


def _api_alias_route(route: APIRoute, prefix: str = "/api") -> APIRoute | None:
    """为 AI 路由增加 /api 前缀别名，便于不经 Vite rewrite 直接访问。"""
    path = route.path or ""
    if not path.startswith("/"):
        path = f"/{path}"
    if path == prefix or path.startswith(f"{prefix}/"):
        return None
    return APIRoute(
        path=f"{prefix}{path}",
        endpoint=route.endpoint,
        methods=route.methods,
        response_model=route.response_model,
        status_code=route.status_code,
        tags=route.tags,
        dependencies=route.dependencies,
        summary=route.summary,
        description=route.description,
        response_description=route.response_description,
        responses=route.responses,
        deprecated=route.deprecated,
        name=route.name,
        openapi_extra=route.openapi_extra,
    )


def integrate_edu_app(main_app: FastAPI) -> bool:
    """
    把 backend.api.main 中的 AI 路由合并到主 FastAPI 应用。

    合并后前端仍通过 /api/analyze 等访问（Vite 会把 /api 前缀 rewrite 掉）。
    返回 True 表示成功，False 表示 AI 模块未加载（主系统仍可运行）。
    """
    import os

    bootstrap_edu_paths()
    # 合并模式下跳过已废弃的 assignments/peer_review/summative（依赖旧 services）
    os.environ.setdefault("EDU_SKIP_LEGACY_ROUTERS", "1")
    try:
        from backend.api.main import app as edu_app
    except Exception as exc:
        logger.warning("LangGraph AI 模块未加载，仅运行学伴系统 API: %s", exc)
        return False

    existing = {_route_signature(r) for r in main_app.routes if _route_signature(r)}
    added = 0
    for route in edu_app.routes:
        sig = _route_signature(route)
        if sig and sig in existing:
            continue

        if isinstance(route, Mount):
            main_app.mount(route.path, route.app, name=route.name)
        else:
            main_app.router.routes.append(route)
            if isinstance(route, APIRoute):
                alias = _api_alias_route(route)
                alias_sig = _route_signature(alias) if alias else None
                if alias and alias_sig and alias_sig not in existing:
                    main_app.router.routes.append(alias)
                    existing.add(alias_sig)
                    added += 1

        if sig:
            existing.add(sig)
        added += 1

    logger.info("已合并 LangGraph AI 路由 %d 条（/analyze、/group-evaluation 等）", added)
    return True
