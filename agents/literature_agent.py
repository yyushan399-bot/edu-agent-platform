"""文献阅读评估智能体：对照文献原文与学生阅读心得，评估理解深度。"""

from __future__ import annotations

import re

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

import llm_config  # noqa: F401

from llm_config import get_chat_llm
from agents.context_utils import build_reference_context, get_memory_context
from state import HistoryTurn, LearningState, LiteratureNodeUpdate, LiteratureResult


class LiteratureAgentOutput(BaseModel):
    """文献阅读评估 Pydantic 结构化输出。"""

    summary: str = Field(
        description="文献核心内容摘要（研究问题、方法、主要结论），供对照学生理解"
    )
    student_viewpoint: str = Field(
        description="对学生阅读心得中核心观点、论据与结论的客观总结"
    )
    alignment_analysis: str = Field(
        description=(
            "观点一致性：学生观点与文献原文的一致之处、偏差或误读；"
            "若一致性较差，须在本字段末尾提炼文献的核心问题/论点供学生对照参考"
        )
    )
    critical_thinking_score: str = Field(
        description="批判性思维：质疑、比较、证据权衡与局限反思等方面的评价"
    )
    innovation_score: str = Field(
        description="创新性：是否提出合理延伸、跨文献联系或独到见解（非凭空臆造）"
    )
    suggestions: str = Field(description="面向学生的综合形成性评价与阅读指导")
    score: int = Field(
        ge=0,
        le=100,
        description=(
            "百分制综合评分（0-100），综合观点一致性、批判性思维、创新性三项加权得出"
        ),
    )


_parser = PydanticOutputParser(pydantic_object=LiteratureAgentOutput)

_REFLECTION_LABEL_HINTS = ("用户补充", "阅读心得", "学生心得", "文字")
_LITERATURE_LABEL_HINTS = ("文档", "第", "页", "pdf", "docx")

LITERATURE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是一位文献阅读与学术写作评估专家，负责判断学生是否真正理解所读文献。\n"
            "你将收到「文献原文（PDF 等解析文本）」与「学生阅读心得」两部分内容，"
            "以及可选的参考资料。请严格对照文献原文评估学生心得，不要编造文献中未出现的观点。\n"
            "若参考资料含领域背景资料，可辅助判断学科惯例与常见误读，"
            "但不要单独罗列「联网研究」小节，也不要出现链接或来源名称。\n"
            "若提供历史评估参考，请对照过往分数与反馈，识别进步与仍存在的薄弱点，"
            "避免重复建议已在历史中解决的问题；不要向学生复述「根据历史记录」等表述。\n"
            "评估维度：\n"
            "1. summary：简要概括文献的研究问题、方法与主要结论\n"
            "2. student_viewpoint：客观总结学生在心得中的核心观点、论据与结论\n"
            "3. alignment_analysis（观点一致性）：分析一致/偏差/误读；"
            "若一致性较差，须在本字段末尾列出 2～4 条「文献核心问题/论点」供学生重新阅读对照\n"
            "4. critical_thinking_score（批判性思维）：评价质疑、比较、证据权衡与局限反思\n"
            "5. innovation_score（创新性）：评价合理延伸、跨文献联系或独到见解（非凭空臆造）\n"
            "6. suggestions：面向学生的综合形成性评价与阅读指导，具体可操作\n"
            "7. score：0-100 整数百分制综合分，须综合观点一致性、批判性思维、创新性三项加权得出；"
            "三项均优秀时可给 85-100，有明显误读或硬伤时应低于 60，并确保与 suggestions 语气一致。\n"
            "若文献原文缺失，请主要依据学生心得评估并明确说明无法对照原文的限制。\n"
            "若学生使用中文作答，请用中文回复；若使用英文，请用英文回复。\n"
            "你必须只输出 JSON，不要输出 markdown 代码块或其它说明文字。\n"
            "{format_instructions}",
        ),
        (
            "human",
            "历史评估参考（若有，含过往分数与反馈）：\n{memory_context}\n\n"
            "参考资料（可选）：\n{reference_context}\n\n"
            "文献原文：\n{literature_content}\n\n"
            "学生阅读心得：\n{student_reflection}",
        ),
    ]
).partial(format_instructions=_parser.get_format_instructions())


def _clamp_score(value: int | float) -> float:
    return float(max(0, min(100, round(float(value)))))


def _to_literature_result(output: LiteratureAgentOutput) -> LiteratureResult:
    return {
        "summary": str(output.summary),
        "student_viewpoint": str(output.student_viewpoint),
        "alignment_analysis": str(output.alignment_analysis),
        "critical_thinking_score": str(output.critical_thinking_score),
        "innovation_score": str(output.innovation_score),
        "suggestions": str(output.suggestions),
        "score": _clamp_score(output.score),
    }


def _strip_multimodal_header(text: str) -> str:
    """去掉 MultimodalProcessor 生成的最外层标题行。"""
    lines = text.splitlines()
    if lines and lines[0].startswith("【多模态输入：") and lines[0].endswith("】"):
        return "\n".join(lines[1:]).strip()
    return text.strip()


def _parse_sectioned_input(text: str) -> tuple[str, str]:
    """
    从 student_input 分离文献正文与阅读心得。

    约定：文档块（PDF/DOCX 解析）→ 文献原文；文字/用户补充块 → 阅读心得。
    """
    body = _strip_multimodal_header(text)
    if not body:
        return "", ""

    section_pattern = re.compile(
        r"^=== \[([^\]]+)\].*===$",
        re.MULTILINE,
    )
    matches = list(section_pattern.finditer(body))
    if not matches:
        return body, ""

    reflection_parts: list[str] = []
    literature_parts: list[str] = []

    for index, match in enumerate(matches):
        label = match.group(1)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        content = body[start:end].strip()
        if not content:
            continue

        is_literature = any(hint in label for hint in _LITERATURE_LABEL_HINTS)
        is_reflection = any(hint in label for hint in _REFLECTION_LABEL_HINTS)

        if is_literature and not is_reflection:
            literature_parts.append(content)
        elif is_reflection and not is_literature:
            reflection_parts.append(content)
        elif is_literature:
            literature_parts.append(content)
        else:
            literature_parts.append(content)

    literature = "\n\n".join(literature_parts).strip()
    reflection = "\n\n".join(reflection_parts).strip()

    if literature and reflection:
        return literature, reflection
    if literature:
        return literature, ""
    if reflection:
        return "", reflection
    return body, ""


def extract_literature_inputs(state: LearningState) -> tuple[str, str]:
    """
    从 state 提取文献原文与学生阅读心得。

    优先使用显式字段 literature_content / student_reflection；
    否则从 student_input 按多模态分块规则解析。
    """
    literature = (state.get("literature_content") or "").strip()
    reflection = (state.get("student_reflection") or "").strip()
    if literature or reflection:
        return literature, reflection

    student_input = (state.get("student_input") or "").strip()
    if not student_input:
        return "", ""
    return _parse_sectioned_input(student_input)


def build_literature_chain(
    model: str | None = None,
    temperature: float | None = None,
):
    llm = get_chat_llm(model=model, temperature=temperature)
    return LITERATURE_PROMPT | llm | _parser


def _format_api_error(exc: Exception) -> str:
    msg = str(exc)
    if "402" in msg or "Insufficient Balance" in msg:
        return "DeepSeek 账户余额不足（HTTP 402），请充值后重试。"
    if "401" in msg or "invalid_api_key" in msg.lower():
        return "API 密钥无效（HTTP 401），请检查 OPENAI_API_KEY。"
    return f"文献阅读评估 API 调用失败。原始错误: {exc}"


def evaluate_literature(
    literature_content: str,
    student_reflection: str,
    *,
    reference_context: str | None = None,
    memory_context: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> LiteratureAgentOutput:
    literature_content = (literature_content or "").strip()
    student_reflection = (student_reflection or "").strip()
    if not literature_content and not student_reflection:
        raise ValueError("文献原文与学生阅读心得不能同时为空")

    if not reference_context:
        reference_context = "（无额外参考资料。）"
    if not memory_context:
        from agents.context_utils import EMPTY_MEMORY_CONTEXT

        memory_context = EMPTY_MEMORY_CONTEXT

    chain = build_literature_chain(model=model, temperature=temperature)
    try:
        return chain.invoke(
            {
                "literature_content": literature_content or "（未提供文献原文。）",
                "student_reflection": student_reflection or "（未提供阅读心得。）",
                "reference_context": reference_context,
                "memory_context": memory_context,
            }
        )
    except Exception as exc:
        raise RuntimeError(_format_api_error(exc)) from exc


def evaluate_literature_json(
    literature_content: str,
    student_reflection: str,
    *,
    reference_context: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> LiteratureResult:
    output = evaluate_literature(
        literature_content,
        student_reflection,
        reference_context=reference_context,
        model=model,
        temperature=temperature,
    )
    return _to_literature_result(output)


def literature_node(state: LearningState) -> LiteratureNodeUpdate:
    literature_content, student_reflection = extract_literature_inputs(state)
    if not literature_content and not student_reflection:
        raise ValueError("无法从 state 解析文献原文或学生阅读心得")

    reference_context = build_reference_context(state, "literature")
    memory_context = get_memory_context(state)
    output = evaluate_literature(
        literature_content,
        student_reflection,
        reference_context=reference_context,
        memory_context=memory_context,
    )
    literature_result = _to_literature_result(output)

    return {
        "literature_result": literature_result,
        "history_memory": [
            {"role": "literature_agent", "content": literature_result["suggestions"]},
        ],
    }


__all__ = [
    "LiteratureAgentOutput",
    "LITERATURE_PROMPT",
    "build_literature_chain",
    "evaluate_literature",
    "evaluate_literature_json",
    "extract_literature_inputs",
    "literature_node",
]
