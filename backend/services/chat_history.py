"""读取学生 AI 会话记录（memory/sessions JSON）。"""

from __future__ import annotations

from typing import Any


def _attach_student_to_session(session_id: str, student_id: str | None) -> None:
    """确保会话 JSON 上带有 student_id，便于教师端按学号检索。"""
    sid = (student_id or "").strip()
    if not sid:
        return
    from memory.session_manager import load_session, save_session

    try:
        data = load_session(session_id, create_if_missing=True)
    except FileNotFoundError:
        return
    if (data.get("student_id") or "").strip():
        return
    data["student_id"] = sid
    save_session(data)
    # 同步 SessionManager 内部目录（默认相同）


def append_session_exchange(
    session_id: str,
    *,
    student_id: str | None,
    user_content: str,
    user_meta: dict[str, Any] | None = None,
    assistant_content: str | None = None,
    assistant_meta: dict[str, Any] | None = None,
) -> None:
    """写入一轮 user/assistant 对话到 session 文件。"""
    active_id = (session_id or "").strip()
    if not active_id:
        return

    from memory.session_manager import SessionManager, load_session, save_session

    _attach_student_to_session(active_id, student_id)

    session_data = load_session(active_id, create_if_missing=True)
    meta = dict(session_data.get("meta") or {})
    title_seed = (user_content or "").strip()
    if meta.get("title") in (None, "", "新会话", "AI 学伴对话", "AI 作业分析对话") and title_seed:
        meta["title"] = title_seed[:32] + ("…" if len(title_seed) > 32 else "")
        session_data["meta"] = meta
        save_session(session_data)

    manager = SessionManager(active_id)
    manager.save_message("user", user_content, meta=user_meta or {})
    if assistant_content and assistant_content.strip():
        manager.save_message("assistant", assistant_content.strip(), meta=assistant_meta or {})


def resolve_or_create_session_id(
    session_id: str | None,
    student_id: str | None,
    *,
    title: str = "AI 作业分析对话",
) -> str:
    """若未传 session_id 但有 student_id，则自动创建会话。"""
    active = (session_id or "").strip()
    if active:
        return active
    sid = (student_id or "").strip()
    if not sid:
        return ""
    from memory.session_manager import SessionManager

    manager = SessionManager.create_session(
        student_id=sid,
        meta={"title": (title or "AI 作业分析对话").strip() or "AI 作业分析对话"},
    )
    return manager.session_id


def get_student_chat_messages(student_id: str, *, limit: int = 300) -> dict[str, Any]:
    """按学号聚合所有会话消息。"""
    sid = (student_id or "").strip()
    if not sid:
        raise ValueError("student_id 不能为空")

    try:
        from memory.session_manager import SessionManager, list_sessions
    except ImportError as exc:
        raise RuntimeError("无法加载 memory.session_manager，请从项目根目录启动后端") from exc

    summaries = [
        s
        for s in list_sessions(limit=500)
        if str(s.get("student_id") or "") == sid
    ]
    non_empty_sessions = [s for s in summaries if int(s.get("message_count") or 0) > 0]
    messages: list[dict[str, Any]] = []
    for summary in non_empty_sessions:
        session_id = str(summary.get("session_id") or "")
        if not session_id:
            continue
        try:
            manager = SessionManager(session_id)
            for msg in manager.load_history():
                messages.append(
                    {
                        **msg,
                        "session_id": session_id,
                        "session_title": summary.get("title") or "会话",
                    }
                )
        except (ValueError, FileNotFoundError):
            continue

    messages.sort(key=lambda m: str(m.get("timestamp") or ""))
    cap = max(1, min(limit, 1000))
    if len(messages) > cap:
        messages = messages[-cap:]

    return {
        "student_id": sid,
        "session_count": len(non_empty_sessions),
        "empty_session_count": len(summaries) - len(non_empty_sessions),
        "message_count": len(messages),
        "messages": messages,
    }
