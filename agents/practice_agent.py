"""实践评估智能体：RAG 增强 + LangChain 对学生实验/操作类内容进行四维评估。"""

from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

import llm_config  # noqa: F401

from llm_config import get_chat_llm
from rag.practice_rag import retrieve_practice_context
from agents.context_utils import build_reference_context, get_memory_context
from state import HistoryTurn, LearningState, PracticeNodeUpdate, PracticeResult


class PracticeAgentOutput(BaseModel):
    """实践评估 Pydantic 结构化输出。"""

    experiment_design: str = Field(
        description="实验/实践方案设计的合理性、完整性与创新性"
    )
    operation_standard: str = Field(
        description="操作步骤、规范性与安全意识的符合程度"
    )
    problem_solving: str = Field(
        description="问题解决能力：遇到问题时的分析、排查与解决思路"
    )
    feedback: str = Field(description="面向学生的综合形成性评价与改进建议")
    score: int = Field(
        ge=0,
        le=100,
        description=(
            "百分制综合评分（0-100），综合实验设计、操作规范、问题解决三项加权得出"
        ),
    )


_parser = PydanticOutputParser(pydantic_object=PracticeAgentOutput)

PRACTICE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是一位教育实践评估专家，负责对学生提交的实验、操作或实践类内容进行专业评估。\n"
            "请结合「参考资料」与「学生提交内容」进行评估；参考资料仅作对照，"
            "不要编造未出现的信息。\n"
            "若参考资料含领域背景资料，请将其中的实验规范、安全要点、常见做法自然融入 feedback，"
            "形成更丰富的形成性评价；不要单独罗列「联网研究」小节，也不要出现链接或来源名称。\n"
            "若提供历史评估参考，请对照过往分数与反馈，识别进步与仍存在的薄弱点，"
            "避免重复建议已在历史中解决的问题；不要向学生复述「根据历史记录」等表述。\n"
            "评估维度：\n"
            "1. experiment_design（实验设计）：目标、变量、步骤、可行性与创新性\n"
            "2. operation_standard（操作规范）：流程是否清晰、安全、可复现\n"
            "3. problem_solving（问题解决）：问题发现、分析与解决思路\n"
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
            "参考资料（实践知识库检索）：\n{reference_context}\n\n"
            "学生提交内容：\n{student_input}",
        ),
    ]
).partial(format_instructions=_parser.get_format_instructions())


def _clamp_score(value: int | float) -> float:
    return float(max(0, min(100, round(float(value)))))


def _to_practice_result(output: PracticeAgentOutput) -> PracticeResult:
    return {
        "experiment_design": str(output.experiment_design),
        "operation_standard": str(output.operation_standard),
        "problem_solving": str(output.problem_solving),
        "feedback": str(output.feedback),
        "score": _clamp_score(output.score),
    }


def build_practice_chain(
    model: str | None = None,
    temperature: float | None = None,
):
    llm = get_chat_llm(model=model, temperature=temperature)
    return PRACTICE_PROMPT | llm | _parser


def _format_api_error(exc: Exception) -> str:
    msg = str(exc)
    if "402" in msg or "Insufficient Balance" in msg:
        return "DeepSeek 账户余额不足（HTTP 402），请充值后重试。"
    if "401" in msg or "invalid_api_key" in msg.lower():
        return "API 密钥无效（HTTP 401），请检查 OPENAI_API_KEY。"
    return f"实践评估 API 调用失败。原始错误: {exc}"


def evaluate_practice(
    student_input: str,
    *,
    reference_context: str | None = None,
    memory_context: str | None = None,
    use_rag: bool = True,
    model: str | None = None,
    temperature: float | None = None,
) -> PracticeAgentOutput:
    if use_rag and reference_context is None:
        reference_context = retrieve_practice_context(student_input)
    if not reference_context:
        reference_context = "（未启用实践知识库检索。）"
    if not memory_context:
        from agents.context_utils import EMPTY_MEMORY_CONTEXT

        memory_context = EMPTY_MEMORY_CONTEXT

    chain = build_practice_chain(model=model, temperature=temperature)
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


def evaluate_practice_json(
    student_input: str,
    *,
    reference_context: str | None = None,
    use_rag: bool = True,
    model: str | None = None,
    temperature: float | None = None,
) -> dict:
    output = evaluate_practice(
        student_input,
        reference_context=reference_context,
        use_rag=use_rag,
        model=model,
        temperature=temperature,
    )
    return _to_practice_result(output)


def practice_node(state: LearningState) -> PracticeNodeUpdate:
    student_input = (state.get("student_input") or "").strip()
    if not student_input:
        raise ValueError("student_input 不能为空")

    reference_context = build_reference_context(state, "practice")
    memory_context = get_memory_context(state)
    output = evaluate_practice(
        student_input,
        reference_context=reference_context,
        memory_context=memory_context,
        use_rag=False,
    )
    practice_result = _to_practice_result(output)

    return {
        "practice_result": practice_result,
        "history_memory": [
            {"role": "practice_agent", "content": practice_result["feedback"]},
        ],
    }


__all__ = [
    "PracticeAgentOutput",
    "PRACTICE_PROMPT",
    "build_practice_chain",
    "evaluate_practice",
    "evaluate_practice_json",
    "practice_node",
]
