"""综合反馈智能体：汇总多路由评估结果，生成 final_feedback。"""



from __future__ import annotations



import json



from langchain_core.prompts import ChatPromptTemplate

from pydantic import BaseModel, Field



import llm_config  # noqa: F401



from agents.context_utils import get_memory_context, get_research_context
from llm_config import get_chat_llm

from state import HistoryTurn, LearningState, ROUTE_LABELS, get_active_routes





class SynthesisAgentOutput(BaseModel):

    final_feedback: str = Field(description="面向学生的综合形成性评价与改进建议")





SYNTHESIS_PROMPT = ChatPromptTemplate.from_messages(

    [

        (

            "system",

            "你是教育评估综合反馈专家。根据学生原始作答、历史评估参考、领域背景资料、已执行的路由分支及各维度评估结果，"
            "生成一段清晰、鼓励性且可操作的**形成性评价**（final_feedback）。\n"
            "**本次仅输出形成性反馈**：聚焦当前作业内容与各路由评估结果，不要输出协作能力终结性评语、"
            "不要讨论自评/互评校准或课程总评结论。\n"
            "若提供了历史评估参考，可对照过往形成性分数与反馈点出进步与薄弱项；"
            "注意区分分数尺度：四路由形成性为 1–5 分（量规二级指标均值），PBL/章节反馈同为 1–5，不可混为一谈。"
            "避免重复已在历史中解决过的建议；不要向学生暴露「历史记录」等内部表述。\n"
            "若提供了领域背景资料，将其中的学科要点自然融入评价，帮助学生对照标准实践与常见误区；"
            "不要向学生暴露网页链接、来源名称或「根据搜索」等表述，也不要单独列出「联网研究」小节。\n"
            "若多个分支均有结果，请整合各域优点与不足，避免重复。\n"
            "你必须只输出 json 结构化结果，包含 final_feedback 字段。",

        ),

        (

            "human",

            "学生提交内容：\n{student_input}\n\n"
            "学生自评（0-5 分，若有）：\n{self_assessment_note}\n\n"
            "已执行路由：{routes_label}\n\n"
            "历史评估参考（若有，含过往分数与反馈）：\n{memory_context}\n\n"
            "领域背景资料（若有，请融入评价，勿暴露来源）：\n{research_context}\n\n"
            "评估结果（JSON）：\n{evaluation_json}",

        ),

    ]

)





def _has_meaningful_theory(result: object) -> bool:

    if not isinstance(result, dict):

        return bool(result)

    return bool((result.get("feedback") or "").strip())





def _has_meaningful_practice(result: object) -> bool:

    if not isinstance(result, dict):

        return bool(result)

    return bool((result.get("feedback") or "").strip())





def _has_meaningful_data(result: object) -> bool:

    if not isinstance(result, dict):

        return bool(result)

    return bool((result.get("feedback") or "").strip())





def _has_meaningful_literature(result: object) -> bool:

    if not isinstance(result, dict):

        return bool(result)

    return bool((result.get("suggestions") or "").strip())





def _collect_evaluation(state: LearningState) -> dict:

    routes = get_active_routes(state)

    payload: dict = {

        "routes": routes,

        "route": routes[0] if routes else "theory",

    }

    total_score = state.get("total_score")
    if total_score is not None:
        payload["total_score"] = total_score
    score_detail = state.get("score_detail")
    if score_detail:
        payload["score_detail"] = score_detail



    if "theory" in routes and _has_meaningful_theory(state.get("theory_result")):

        payload["theory_result"] = state["theory_result"]

    if "practice" in routes and _has_meaningful_practice(state.get("practice_result")):

        payload["practice_result"] = state["practice_result"]

    if "data" in routes and _has_meaningful_data(state.get("data_result")):

        payload["data_result"] = state["data_result"]

    if "literature" in routes and _has_meaningful_literature(
        state.get("literature_result")
    ):

        payload["literature_result"] = state["literature_result"]



    if len(payload) <= 2:

        if state.get("theory_result"):

            payload["theory_result"] = state["theory_result"]

        if state.get("practice_result"):

            payload["practice_result"] = state["practice_result"]

        if state.get("data_result"):

            payload["data_result"] = state["data_result"]

        if state.get("literature_result"):

            payload["literature_result"] = state["literature_result"]



    return payload





def build_synthesis_chain(

    model: str | None = None,

    temperature: float | None = None,

):

    llm = get_chat_llm(model=model, temperature=temperature)

    structured_llm = llm.with_structured_output(

        SynthesisAgentOutput,

        method="json_mode",

    )

    return SYNTHESIS_PROMPT | structured_llm





def synthesis_node(state: LearningState) -> dict:

    student_input = (state.get("student_input") or "").strip()

    if not student_input:

        raise ValueError("student_input 不能为空")



    evaluation = _collect_evaluation(state)

    routes = evaluation.get("routes", ["theory"])

    routes_label = ", ".join(ROUTE_LABELS.get(r, r) for r in routes)
    research_context = get_research_context(state) or "（无额外领域背景资料。）"
    memory_context = get_memory_context(state)

    self_assessment_note = "（学生未填写自评）"
    raw_self = state.get("self_score")
    if raw_self is not None:
        try:
            self_val = float(raw_self)
            if 0.0 <= self_val <= 5.0:
                self_assessment_note = (
                    f"{self_val:g} 分。请在反馈末尾用 1～2 句话对照自评与系统评估，"
                    "帮助学生校准自我认知（勿展开终结性/互评话题）。"
                )
        except (TypeError, ValueError):
            pass

    chain = build_synthesis_chain()
    try:
        result = chain.invoke(
            {
                "student_input": student_input,
                "self_assessment_note": self_assessment_note,
                "routes_label": routes_label,
                "memory_context": memory_context,
                "research_context": research_context,
                "evaluation_json": json.dumps(

                    evaluation, ensure_ascii=False, indent=2

                ),

            }

        )

    except Exception as exc:

        raise RuntimeError(f"综合反馈生成失败: {exc}") from exc



    feedback = str(result.final_feedback)

    return {

        "final_feedback": feedback,

        "history_memory": [

            {"role": "synthesis_agent", "content": feedback},

        ],

    }





__all__ = [

    "SynthesisAgentOutput",

    "SYNTHESIS_PROMPT",

    "build_synthesis_chain",

    "synthesis_node",

]

