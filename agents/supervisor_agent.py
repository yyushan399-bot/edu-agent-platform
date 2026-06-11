"""LLM Router：根据学生提交内容自动分类到单一评估分支。"""

from __future__ import annotations

from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, field_validator

import llm_config  # noqa: F401

from llm_config import get_chat_llm
from state import LearningState, SupervisorNodeUpdate, normalize_route, normalize_routes

RouteType = Literal["theory", "practice", "data_analysis", "literature"]


class RouterOutput(BaseModel):
    """LLM Router 结构化输出。"""

    route: RouteType = Field(
        description=(
            "评估分支，只能是一个值：theory / practice / data_analysis / literature"
        )
    )
    reason: str = Field(
        description="选择该路由的简要理由，面向教师或系统日志，一句话说明"
    )

    @field_validator("route", mode="before")
    @classmethod
    def normalize_route_field(cls, value: object) -> str:
        if value is None:
            return "theory"
        raw = str(value).strip().lower()
        if raw == "data":
            return "data_analysis"
        return raw

    @property
    def canonical_route(self) -> str:
        """映射为图内使用的 canonical 路由名（如 data_analysis → data）。"""
        return normalize_route(self.route)


ROUTER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是教育智能体系统的 LLM Router，负责根据学生提交内容判断应进入哪一个评估分支。\n"
            "你只能输出 json 结构化结果，包含 route 与 reason 两个字段。\n"
            "route 只能是以下四选一（小写英文）：\n"
            "- theory：理论分析、概念理解、原理阐述、公式推导、论证逻辑\n"
            "- practice：实验实践、操作步骤、实验设计、动手操作、规范与安全\n"
            "- data_analysis：数据分析、统计处理、图表可视化、建模推断\n"
            "- literature：论文/文献阅读、阅读心得、文献综述、引用与观点对照\n"
            "规则：\n"
            "1. 每次只选择一个最匹配的分支，不要返回多个类别。\n"
            "2. reason 用一句中文简要说明判断依据，例如「学生提交的是论文阅读心得」。\n"
            "3. 若同时涉及多类内容，选择最主要、占比最高的一类。\n"
            "4. 若上传 PDF 文献并附带阅读感想，优先选择 literature。",
        ),
        ("human", "学生提交内容：\n{student_input}"),
    ]
)

# 兼容旧引用
SUPERVISOR_PROMPT = ROUTER_PROMPT


def build_router_chain(
    model: str | None = None,
    temperature: float | None = None,
):
    llm = get_chat_llm(model=model, temperature=temperature)
    structured_llm = llm.with_structured_output(
        RouterOutput,
        method="json_mode",
    )
    return ROUTER_PROMPT | structured_llm


def build_supervisor_chain(
    model: str | None = None,
    temperature: float | None = None,
):
    """兼容旧函数名。"""
    return build_router_chain(model=model, temperature=temperature)


def _format_api_error(exc: Exception) -> str:
    msg = str(exc)
    if "402" in msg or "Insufficient Balance" in msg:
        return "DeepSeek 账户余额不足（HTTP 402），请充值后重试。"
    if "401" in msg or "invalid_api_key" in msg.lower():
        return "API 密钥无效（HTTP 401），请检查 OPENAI_API_KEY。"
    return f"路由判断 API 调用失败。原始错误: {exc}"


def route_student_input(
    student_input: str,
    *,
    model: str | None = None,
    temperature: float | None = None,
) -> RouterOutput:
    """调用 LLM Router，返回 route + reason。"""
    chain = build_router_chain(model=model, temperature=temperature)
    try:
        return chain.invoke({"student_input": student_input})
    except Exception as exc:
        raise RuntimeError(_format_api_error(exc)) from exc


def supervisor_node(state: LearningState) -> SupervisorNodeUpdate:
    student_input = (state.get("student_input") or "").strip()
    if not student_input:
        raise ValueError("student_input 不能为空")

    preset = state.get("routes")
    if preset:
        routes = normalize_routes(preset)
        route = routes[0]
        reason = (state.get("route_reason") or "").strip() or "（用户预设路由）"
    else:
        result = route_student_input(student_input)
        route = result.canonical_route
        routes = [route]
        reason = result.reason.strip() or "（未提供路由理由）"

    return {
        "routes": routes,
        "route": route,
        "route_reason": reason,
    }


__all__ = [
    "RouteType",
    "RouterOutput",
    "ROUTER_PROMPT",
    "SUPERVISOR_PROMPT",
    "build_router_chain",
    "build_supervisor_chain",
    "route_student_input",
    "supervisor_node",
]
