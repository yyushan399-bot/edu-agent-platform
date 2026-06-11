"""Graph 节点：按 session_id 加载会话历史，写入 chat_history。"""

from __future__ import annotations

from typing import TypedDict

from memory.session_manager import SessionManager
from state import HistoryTurn, LearningState


class LoadMemoryNodeUpdate(TypedDict, total=False):
    chat_history: list[HistoryTurn]


def _messages_to_chat_history(messages: list[dict]) -> list[HistoryTurn]:
    """将会话消息转为 state.chat_history 条目。"""
    history: list[HistoryTurn] = []
    for index, message in enumerate(messages, start=1):
        role = str(message.get("role") or "").strip()
        content = str(message.get("content") or "").strip()
        if not role or not content:
            continue
        turn: HistoryTurn = {"role": role, "content": content}
        message_id = str(message.get("message_id") or "").strip()
        if message_id:
            turn["turn_id"] = index
        history.append(turn)
    return history


def load_session_chat_history(
    session_id: str,
    *,
    limit: int | None = None,
) -> list[HistoryTurn]:
    """不经过图，直接按 session_id 加载 chat_history。"""
    session_id = (session_id or "").strip()
    if not session_id:
        return []

    try:
        manager = SessionManager(session_id)
        messages = manager.load_history(limit=limit)
    except (ValueError, FileNotFoundError):
        return []

    return _messages_to_chat_history(messages)


def load_memory_node(state: LearningState) -> LoadMemoryNodeUpdate:
    """
    根据 state.session_id 读取会话历史消息，写入 chat_history。

    无 session_id 或会话不存在时返回空列表。
    """
    session_id = (state.get("session_id") or "").strip()
    if not session_id:
        return {"chat_history": []}

    chat_history = load_session_chat_history(session_id)
    return {"chat_history": chat_history}


__all__ = [
    "LoadMemoryNodeUpdate",
    "load_memory_node",
    "load_session_chat_history",
]
