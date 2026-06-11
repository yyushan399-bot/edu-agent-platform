"""使用 LLM 总结单页与多页研究内容（不向学生暴露网页原文）。"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from llm_config import get_chat_llm

PAGE_SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是内部教研分析助手。根据网页正文提炼与教育评估相关的核心知识点，"
            "供教师后台参考。\n"
            "要求：\n"
            "1. 用中文条目式总结，200～400 字\n"
            "2. 不要输出 URL、网站名、广告或导航信息\n"
            "3. 不要复述大段原文",
        ),
        (
            "human",
            "页面标题：{title}\n\n"
            "网页正文（已清洗）：\n{body}",
        ),
    ]
)

MERGE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是内部教研分析助手。将多来源网页摘要合并为一份「联网研究上下文」，"
            "用于后续对学生作业进行理论/实践/数据评估。\n"
            "要求：\n"
            "1. 去重、结构化（可分点）\n"
            "2. 不出现 URL、来源站点名称\n"
            "3. 总长度 400～800 字\n"
            "4. 只输出正文，不要标题前缀",
        ),
        (
            "human",
            "学生提交主题（节选）：\n{student_input}\n\n"
            "各页摘要：\n{page_summaries}",
        ),
    ]
)


def summarize_page(title: str, body: str) -> str:
    if not body.strip():
        return ""
    llm = get_chat_llm(temperature=0.2)
    chain = PAGE_SUMMARY_PROMPT | llm
    result = chain.invoke(
        {
            "title": title or "（无标题）",
            "body": body[:6000],
        }
    )
    return str(result.content).strip()


def merge_page_summaries(student_input: str, summaries: list[str]) -> str:
    valid = [s for s in summaries if s.strip()]
    if not valid:
        return ""
    if len(valid) == 1:
        return valid[0]
    llm = get_chat_llm(temperature=0.2)
    chain = MERGE_PROMPT | llm
    joined = "\n\n---\n\n".join(
        f"【来源{i + 1}】\n{text}" for i, text in enumerate(valid)
    )
    result = chain.invoke(
        {
            "student_input": (student_input or "")[:1500],
            "page_summaries": joined[:12000],
        }
    )
    return str(result.content).strip()


__all__ = ["merge_page_summaries", "summarize_page"]
