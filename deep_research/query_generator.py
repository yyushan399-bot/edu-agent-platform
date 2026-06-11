"""根据 student_input 生成研究检索词。"""

from __future__ import annotations

import json
import re

from langchain_core.prompts import ChatPromptTemplate

from llm_config import get_chat_llm

QUERY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是教育研究助手。根据学生提交的学习内容，生成 1～3 个适合中文网页搜索的检索词。\n"
            "要求：\n"
            "1. 检索词应帮助查找相关知识点、教材背景、常见误区或实践案例\n"
            "2. 使用简体中文，每条不超过 30 字\n"
            "3. 只输出 JSON 数组，例如 [\"检索词1\", \"检索词2\"]，不要其它文字",
        ),
        ("human", "学生提交内容：\n{student_input}"),
    ]
)


def generate_research_queries(
    student_input: str,
    *,
    max_queries: int = 3,
) -> list[str]:
    """使用 LLM 从学生作答生成博查搜索 query 列表。"""
    text = (student_input or "").strip()
    if not text:
        return []

    llm = get_chat_llm(temperature=0.1)
    chain = QUERY_PROMPT | llm
    raw = chain.invoke({"student_input": text[:4000]}).content
    content = str(raw).strip()

    queries: list[str] = []
    try:
        match = re.search(r"\[[\s\S]*\]", content)
        if match:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                queries = [str(q).strip() for q in parsed if str(q).strip()]
    except json.JSONDecodeError:
        pass

    if not queries:
        line = content.splitlines()[0].strip(" `\"'[]")
        if line:
            queries = [line[:60]]

    if not queries:
        queries = [text[:80]]

    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique[:max_queries]


__all__ = ["generate_research_queries"]
