"""理论评估智能体：RAG 增强 + LangChain 对学生提交内容进行四维评估。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

import llm_config  # noqa: F401  # 导入时加载 .env

from llm_config import get_chat_llm
from rag.theory_rag import retrieve_theory_context
from agents.context_utils import build_reference_context, get_memory_context
from state import HistoryTurn, LearningState, TheoryNodeUpdate, TheoryResult


class TheoryAgentOutput(BaseModel):
    """理论评估结构化输出（JSON 兼容）。"""

    concept_understanding: str = Field(
        description="理论准确性：核心概念理解是否正确、表述是否准确"
    )
    logic: str = Field(
        description="逻辑完整性：论证/推导是否连贯、前提与结论是否自洽"
    )
    critical_thinking: str = Field(
        description="知识深度：是否触及原理层次、能否关联拓展而非停留在表面"
    )
    feedback: str = Field(description="面向学生的综合形成性评价与改进建议")
    score: int = Field(
        ge=0,
        le=100,
        description=(
            "百分制综合评分（0-100），综合理论准确性、逻辑完整性、知识深度三项加权得出"
        ),
    )


_parser = PydanticOutputParser(pydantic_object=TheoryAgentOutput)

THEORY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是一位教育评估专家，负责对学生提交的理论/概念类内容进行专业评估。\n"
            "请结合「参考资料」与「学生提交内容」进行评估；参考资料仅作对照，"
            "若与学生作答冲突，以指出差异并说明理由为主，不要编造未出现的信息。\n"
            "若参考资料含领域背景资料，请将其中的学科要点、常见误区、标准做法自然融入 feedback，"
            "形成更丰富的形成性评价；不要单独罗列「联网研究」小节，也不要出现链接或来源名称。\n"
            "若提供历史评估参考，请对照过往分数与反馈，识别进步与仍存在的薄弱点，"
            "避免重复建议已在历史中解决的问题；不要向学生复述「根据历史记录」等表述。\n"
            "评估维度：\n"
            "1. concept_understanding（理论准确性）：概念与原理是否正确、有无明显误读\n"
            "2. logic（逻辑完整性）：论证/推导是否连贯，前提、推理与结论是否自洽\n"
            "3. critical_thinking（知识深度）：是否触及原理层次，能否关联、拓展或比较\n"
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
            "参考资料（理论知识库检索）：\n{reference_context}\n\n"
            "学生提交内容：\n{student_input}",
        ),
    ]
).partial(format_instructions=_parser.get_format_instructions())


def _clamp_score(value: int | float) -> float:
    """将评分限制在 0-100 并转为 float。"""
    return float(max(0, min(100, round(float(value)))))


def _to_theory_result(output: TheoryAgentOutput) -> TheoryResult:
    """将 Pydantic 输出转为 LearningState.theory_result 所需结构。"""
    return {
        "concept_understanding": str(output.concept_understanding),
        "logic": str(output.logic),
        "critical_thinking": str(output.critical_thinking),
        "feedback": str(output.feedback),
        "score": _clamp_score(output.score),
    }


def build_theory_chain(
    model: str | None = None,
    temperature: float | None = None,
):
    """构建理论评估链：Prompt + ChatOpenAI + Pydantic 解析（兼容 DeepSeek）。"""
    llm = get_chat_llm(model=model, temperature=temperature)
    return THEORY_PROMPT | llm | _parser


def _format_api_error(exc: Exception) -> str:
    """将常见 API 错误转为可读提示。"""
    msg = str(exc)
    if "402" in msg or "Insufficient Balance" in msg:
        return (
            "DeepSeek 账户余额不足（HTTP 402）。请到 https://platform.deepseek.com "
            "充值后再试。当前 API 配置与代码正常，无需修改项目。"
        )
    if "401" in msg or "invalid_api_key" in msg.lower():
        return (
            "API 密钥无效（HTTP 401）。请检查 .env 中 OPENAI_API_KEY 是否为 DeepSeek 密钥。"
        )
    return (
        "理论评估 API 调用失败。请检查 .env 中 OPENAI_API_KEY、"
        "OPENAI_BASE_URL（DeepSeek: https://api.deepseek.com/v1）及网络连接。"
        f" 原始错误: {exc}"
    )


def evaluate_theory(
    student_input: str,
    *,
    reference_context: str | None = None,
    memory_context: str | None = None,
    use_rag: bool = True,
    model: str | None = None,
    temperature: float | None = None,
) -> TheoryAgentOutput:
    """评估学生提交内容；默认先经 theory_rag 检索参考资料。"""
    if use_rag and reference_context is None:
        reference_context = retrieve_theory_context(student_input)
    if not reference_context:
        reference_context = "（未启用理论知识库检索。）"
    if not memory_context:
        from agents.context_utils import EMPTY_MEMORY_CONTEXT

        memory_context = EMPTY_MEMORY_CONTEXT

    chain = build_theory_chain(model=model, temperature=temperature)
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


def evaluate_theory_json(
    student_input: str,
    *,
    reference_context: str | None = None,
    use_rag: bool = True,
    model: str | None = None,
    temperature: float | None = None,
) -> dict:
    """评估学生提交内容，返回 JSON 兼容 dict。"""
    output = evaluate_theory(
        student_input,
        reference_context=reference_context,
        use_rag=use_rag,
        model=model,
        temperature=temperature,
    )
    return _to_theory_result(output)


def theory_node(state: LearningState) -> TheoryNodeUpdate:
    """LangGraph 节点：读取 state 中 RAG 上下文 → 理论评估。"""
    student_input = (state.get("student_input") or "").strip()
    if not student_input:
        raise ValueError("student_input 不能为空")

    reference_context = build_reference_context(state, "theory")
    memory_context = get_memory_context(state)
    output = evaluate_theory(
        student_input,
        reference_context=reference_context,
        memory_context=memory_context,
        use_rag=False,
    )
    theory_result = _to_theory_result(output)

    history_turn: HistoryTurn = {
        "role": "theory_agent",
        "content": theory_result["feedback"],
    }

    return {
        "theory_result": theory_result,
        "history_memory": [history_turn],
    }


__all__ = [
    "TheoryAgentOutput",
    "THEORY_PROMPT",
    "build_theory_chain",
    "evaluate_theory",
    "evaluate_theory_json",
    "theory_node",
]
