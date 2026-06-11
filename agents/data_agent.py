"""数据分析智能体：RAG 增强 + LangChain 对学生数据类内容进行四维评估。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

import llm_config  # noqa: F401

from llm_config import get_chat_llm
from rag.data_rag import retrieve_data_context
from agents.context_utils import build_reference_context, get_memory_context
from state import DataNodeUpdate, DataResult, HistoryTurn, LearningState


class DataAgentOutput(BaseModel):
    """数据分析 Pydantic 结构化输出。"""

    data_analysis: str = Field(
        description="数据分析能力：数据理解、清洗、统计分析与解读的合理性"
    )
    visualization: str = Field(
        description="可视化表达：图表类型选择、标注与可读性"
    )
    modeling: str = Field(
        description="建模严谨性：假设、方法、验证与结论的严谨程度"
    )
    feedback: str = Field(description="面向学生的综合形成性评价与改进建议")
    score: int = Field(
        ge=0,
        le=100,
        description=(
            "百分制综合评分（0-100），综合数据分析、可视化表达、建模严谨性三项加权得出"
        ),
    )


_parser = PydanticOutputParser(pydantic_object=DataAgentOutput)

DATA_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是一位教育数据分析评估专家，负责对学生提交的数据分析、统计或建模类内容进行专业评估。\n"
            "请结合「参考资料」与「学生提交内容」进行评估；参考资料仅作对照，"
            "不要编造未出现的信息。\n"
            "若参考资料含领域背景资料，请将其中的分析范式、可视化与建模要点自然融入 feedback，"
            "形成更丰富的形成性评价；不要单独罗列「联网研究」小节，也不要出现链接或来源名称。\n"
            "若提供历史评估参考，请对照过往分数与反馈，识别进步与仍存在的薄弱点，"
            "避免重复建议已在历史中解决的问题；不要向学生复述「根据历史记录」等表述。\n"
            "评估维度：\n"
            "1. data_analysis（数据分析）：清洗、统计分析与解读是否合理\n"
            "2. visualization（可视化表达）：图表类型、标注、可读性是否清晰有效\n"
            "3. modeling（建模严谨性）：假设、方法、验证与结论是否严谨\n"
            "4. feedback：面向学生的综合形成性评价与改进建议，具体可操作\n"
            "5. score：0-100 整数百分制综合分，须综合以上三项加权得出；"
            "三项均优秀时可给 85-100，有明显硬伤时应低于 60，并确保与 feedback 语气一致。\n"
            "若学生使用中文作答，请用中文回复；若使用英文，请用英文回复。\n"
            "你必须只输出 JSON，不要输出 markdown 代码块或其它说明文字。\n"
            "{format_instructions}",
        ),
        (
            "human",
            "历史评估参考（若有，含过往分数与反馈）：\n{memory_context}\n\n"
            "参考资料（数据知识库检索）：\n{reference_context}\n\n"
            "学生提交内容：\n{student_input}",
        ),
    ]
).partial(format_instructions=_parser.get_format_instructions())


def _clamp_score(value: int | float) -> float:
    return float(max(0, min(100, round(float(value)))))


def _to_data_result(output: DataAgentOutput) -> DataResult:
    return {
        "data_analysis": str(output.data_analysis),
        "visualization": str(output.visualization),
        "modeling": str(output.modeling),
        "feedback": str(output.feedback),
        "score": _clamp_score(output.score),
    }


def _format_api_error(exc: Exception) -> str:
    msg = str(exc)
    if "402" in msg or "Insufficient Balance" in msg:
        return "DeepSeek 账户余额不足（HTTP 402），请充值后重试。"
    if "401" in msg or "invalid_api_key" in msg.lower():
        return "API 密钥无效（HTTP 401），请检查 OPENAI_API_KEY。"
    return f"数据分析 API 调用失败。原始错误: {exc}"


def build_data_chain(
    model: str | None = None,
    temperature: float | None = None,
):
    llm = get_chat_llm(model=model, temperature=temperature)
    return DATA_PROMPT | llm | _parser


def evaluate_data(
    student_input: str,
    *,
    reference_context: str | None = None,
    memory_context: str | None = None,
    use_rag: bool = True,
    model: str | None = None,
    temperature: float | None = None,
) -> DataAgentOutput:
    if use_rag and reference_context is None:
        reference_context = retrieve_data_context(student_input)
    if not reference_context:
        reference_context = "（未启用数据知识库检索。）"
    if not memory_context:
        from agents.context_utils import EMPTY_MEMORY_CONTEXT

        memory_context = EMPTY_MEMORY_CONTEXT

    chain = build_data_chain(model=model, temperature=temperature)
    try:
        return chain.invoke(
            {
                "student_input": student_input,
                "reference_context": reference_context,
                "memory_context": memory_context,
            }
        )
    except Exception as exc:
        raise RuntimeError(_format_api_error(exc)) from exc


def evaluate_data_json(
    student_input: str,
    *,
    reference_context: str | None = None,
    use_rag: bool = True,
    model: str | None = None,
    temperature: float | None = None,
) -> DataResult:
    result = evaluate_data(
        student_input,
        reference_context=reference_context,
        use_rag=use_rag,
        model=model,
        temperature=temperature,
    )
    return _to_data_result(result)


def data_node(state: LearningState) -> DataNodeUpdate:
    student_input = (state.get("student_input") or "").strip()
    if not student_input:
        raise ValueError("student_input 不能为空")

    reference_context = build_reference_context(state, "data")
    memory_context = get_memory_context(state)
    output = evaluate_data(
        student_input,
        reference_context=reference_context,
        memory_context=memory_context,
        use_rag=False,
    )
    data_result = _to_data_result(output)

    return {
        "data_result": data_result,
        "history_memory": [
            {"role": "data_agent", "content": data_result["feedback"]},
        ],
    }


__all__ = [
    "DataAgentOutput",
    "DATA_PROMPT",
    "build_data_chain",
    "evaluate_data",
    "evaluate_data_json",
    "data_node",
]
