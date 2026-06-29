"""终结性评价 API：聚合自评 / 互评 / 智能体分数并调用终结性评价智能体。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from services.collaboration_score_service import build_collaboration_payload
from services.group_service import UserNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/summative-evaluation", tags=["summative-evaluation"])


class SummativeEvaluationRequest(BaseModel):
    user_id: int = Field(..., description="学生 user_id（users.id）")
    assignment_id: int = Field(..., description="作业 ID")
    use_llm: bool = Field(True, description="是否调用 LLM 生成终结性评语")


def run_summative_for_assignment(
    db: Session,
    *,
    user_id: int,
    assignment_id: int,
    use_llm: bool = True,
) -> dict[str, Any] | None:
    """若存在智能体分数，则聚合三分数并运行终结性评价智能体。"""
    collaboration = build_collaboration_payload(
        db,
        user_id=user_id,
        assignment_id=assignment_id,
    )
    if not collaboration.get("ready_for_summative"):
        return None

    from agents.summative_evaluation_agent import run_summative_evaluation

    result = run_summative_evaluation(collaboration, use_llm=use_llm)
    return {
        "user_id": user_id,
        "assignment_id": assignment_id,
        "evaluation_mode": "summative",
        **result,
    }


@router.post("")
async def create_summative_evaluation(
    body: SummativeEvaluationRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    读取指定用户在某作业上的自评、互评与智能体分数，
    作为协作能力输入，调用终结性评价智能体。
    """
    try:
        payload = run_summative_for_assignment(
            db,
            user_id=body.user_id,
            assignment_id=body.assignment_id,
            use_llm=body.use_llm,
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "summative evaluation failed user_id=%s assignment_id=%s",
            body.user_id,
            body.assignment_id,
        )
        raise HTTPException(
            status_code=500,
            detail=f"终结性评价失败: {type(exc).__name__}: {exc}",
        ) from exc

    if payload is None:
        raise HTTPException(
            status_code=404,
            detail="未找到该作业的智能体评估分数，请先提交作业并完成 AI 评估",
        )

    return jsonable_encoder({"success": True, **payload})


@router.get("")
async def get_summative_evaluation(
    user_id: int = Query(..., description="学生 user_id"),
    assignment_id: int = Query(..., description="作业 ID"),
    use_llm: bool = Query(False, description="是否调用 LLM（默认仅规则汇总）"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """查询并生成终结性评价（与 POST 等价，便于调试）。"""
    try:
        collaboration = build_collaboration_payload(
            db,
            user_id=user_id,
            assignment_id=assignment_id,
        )
        payload = run_summative_for_assignment(
            db,
            user_id=user_id,
            assignment_id=assignment_id,
            use_llm=use_llm,
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if payload is None:
        raise HTTPException(
            status_code=404,
            detail="未找到该作业的智能体评估分数",
        )

    return jsonable_encoder(
        {
            "success": True,
            "collaboration_input": collaboration,
            **payload,
        }
    )


__all__ = ["router", "run_summative_for_assignment"]
