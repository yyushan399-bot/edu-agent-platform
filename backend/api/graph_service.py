"""LangGraph 调用封装（不修改 agents/ 下现有实现）。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 项目根目录（empty-window）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def run_langgraph_analysis(
    student_input: str,
    *,
    uploaded_files: list[dict[str, Any]] | None = None,
    routes: list[str] | None = None,
    student_id: str | None = None,
    memory_retrieve_k: int = 3,
    enable_deep_research: bool | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """调用 LangGraph 工作流，返回可 JSON 序列化的 dict。"""
    import llm_config  # noqa: F401
    from llm_config import is_dotenv_loaded

    if not is_dotenv_loaded():
        raise ValueError(
            "未配置 OPENAI_API_KEY。请在项目根目录 .env 中设置 DeepSeek/OpenAI 密钥。"
        )

    from fastapi.encoders import jsonable_encoder
    from main_graph import app as langgraph_app
    from state import create_initial_state

    # API 默认关闭 Deep Research，避免博查/多页抓取导致超时或 500
    if enable_deep_research is None:
        enable_deep_research = False

    initial = create_initial_state(
        student_input,
        uploaded_files=uploaded_files,
        routes=routes,
        student_id=student_id,
        session_id=session_id,
        memory_retrieve_k=memory_retrieve_k,
        enable_deep_research=enable_deep_research,
    )

    logger.info(
        "LangGraph invoke start (routes=%s, deep_research=%s, input_len=%d)",
        initial.get("routes"),
        enable_deep_research,
        len(student_input),
    )

    # ------------------------------------------------------------------
    # LangGraph 调用位置
    # ------------------------------------------------------------------
    result = langgraph_app.invoke(initial)

    logger.info("LangGraph invoke done")
    return jsonable_encoder(dict(result))


__all__ = ["PROJECT_ROOT", "run_langgraph_analysis"]
