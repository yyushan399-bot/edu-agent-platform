"""会话管理：按 session_id 在 JSON 文件中持久化多轮消息。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

DEFAULT_SESSIONS_DIR = Path(__file__).resolve().parent / "sessions"
SESSION_ID_PATTERN = re.compile(
    r"^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$"
)

VALID_MESSAGE_ROLES = frozenset(
    {"user", "assistant", "system", "tool", "agent", "student", "teacher"}
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_session_id(session_id: str) -> str:
    """校验 session_id（UUID 字符串）。"""
    value = (session_id or "").strip()
    if not value:
        raise ValueError("session_id 不能为空")
    if not SESSION_ID_PATTERN.match(value):
        raise ValueError("session_id 必须为有效 UUID")
    return value


def get_session_path(
    session_id: str,
    *,
    sessions_dir: Path | None = None,
) -> Path:
    """返回会话 JSON 文件路径。"""
    safe_id = sanitize_session_id(session_id)
    base = sessions_dir or DEFAULT_SESSIONS_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{safe_id}.json"


def empty_session(
    session_id: str,
    *,
    student_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造空会话结构。"""
    now = _utc_now_iso()
    return {
        "session_id": sanitize_session_id(session_id),
        "student_id": (student_id or "").strip(),
        "created_at": now,
        "updated_at": now,
        "messages": [],
        "meta": dict(meta or {}),
    }


def load_session(
    session_id: str,
    *,
    sessions_dir: Path | None = None,
    create_if_missing: bool = False,
) -> dict[str, Any]:
    """加载会话 JSON。"""
    path = get_session_path(session_id, sessions_dir=sessions_dir)
    if not path.is_file():
        if create_if_missing:
            return empty_session(session_id)
        raise FileNotFoundError(f"会话不存在: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"会话文件格式无效: {path}")

    data.setdefault("session_id", sanitize_session_id(session_id))
    data.setdefault("messages", [])
    data.setdefault("meta", {})
    return data


def save_session(
    session: dict[str, Any],
    *,
    sessions_dir: Path | None = None,
) -> Path:
    """原子写入会话 JSON。"""
    session_id = sanitize_session_id(str(session.get("session_id") or ""))
    path = get_session_path(session_id, sessions_dir=sessions_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = dict(session)
    payload["session_id"] = session_id
    payload["updated_at"] = _utc_now_iso()
    if "created_at" not in payload:
        payload["created_at"] = payload["updated_at"]
    payload.setdefault("messages", [])
    payload.setdefault("meta", {})

    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
    return path


def build_message(
    *,
    role: str,
    content: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造单条消息记录。"""
    role_value = (role or "").strip().lower()
    if role_value not in VALID_MESSAGE_ROLES:
        raise ValueError(
            f"无效 role: {role!r}，允许: {', '.join(sorted(VALID_MESSAGE_ROLES))}"
        )
    text = (content or "").strip()
    if not text:
        raise ValueError("message content 不能为空")

    message: dict[str, Any] = {
        "message_id": str(uuid4()),
        "role": role_value,
        "content": text,
        "timestamp": _utc_now_iso(),
    }
    if meta:
        message["meta"] = dict(meta)
    return message


class SessionManager:
    """
    单次分析会话管理器。

    - 每个 session 对应 memory/sessions/{session_id}.json
    - 支持多轮 save_message / load_history
    """

    def __init__(
        self,
        session_id: str,
        *,
        sessions_dir: Path | str | None = None,
    ) -> None:
        self.session_id = sanitize_session_id(session_id)
        self.sessions_dir = Path(sessions_dir) if sessions_dir else DEFAULT_SESSIONS_DIR

    @property
    def session_path(self) -> Path:
        return get_session_path(self.session_id, sessions_dir=self.sessions_dir)

    @classmethod
    def create_session(
        cls,
        *,
        student_id: str | None = None,
        meta: dict[str, Any] | None = None,
        sessions_dir: Path | str | None = None,
    ) -> SessionManager:
        """创建新会话并持久化空 JSON 文件。"""
        session_id = str(uuid4())
        directory = Path(sessions_dir) if sessions_dir else DEFAULT_SESSIONS_DIR
        session = empty_session(
            session_id,
            student_id=student_id,
            meta=meta,
        )
        save_session(session, sessions_dir=directory)
        return cls(session_id, sessions_dir=directory)

    def load(self) -> dict[str, Any]:
        """加载完整会话对象。"""
        return load_session(self.session_id, sessions_dir=self.sessions_dir)

    def save_message(
        self,
        role: str,
        content: str,
        *,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """追加一条消息并保存。"""
        session = load_session(
            self.session_id,
            sessions_dir=self.sessions_dir,
            create_if_missing=True,
        )
        message = build_message(role=role, content=content, meta=meta)
        messages: list[dict[str, Any]] = list(session.get("messages") or [])
        messages.append(message)
        session["messages"] = messages
        save_session(session, sessions_dir=self.sessions_dir)
        return message

    def load_history(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """返回会话消息列表（按时间顺序）。"""
        session = load_session(self.session_id, sessions_dir=self.sessions_dir)
        messages: list[dict[str, Any]] = list(session.get("messages") or [])
        if offset:
            messages = messages[offset:]
        if limit is not None and limit >= 0:
            messages = messages[-limit:] if limit else []
        return messages

    def clear_messages(self) -> None:
        """清空当前会话消息（保留 session 元数据）。"""
        session = load_session(
            self.session_id,
            sessions_dir=self.sessions_dir,
            create_if_missing=True,
        )
        session["messages"] = []
        save_session(session, sessions_dir=self.sessions_dir)

    def delete(self) -> bool:
        """删除会话文件。"""
        path = self.session_path
        if path.is_file():
            path.unlink()
            return True
        return False


def _derive_session_title(messages: list[dict[str, Any]]) -> str:
    for message in messages:
        if str(message.get("role") or "") == "user":
            text = str(message.get("content") or "").strip()
            if text:
                return text[:32] + ("…" if len(text) > 32 else "")
    return "新会话"


def list_sessions(
    *,
    sessions_dir: Path | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """列出所有会话摘要，按 updated_at 降序。"""
    base = sessions_dir or DEFAULT_SESSIONS_DIR
    if not base.is_dir():
        return []

    items: list[dict[str, Any]] = []
    for path in base.glob("*.json"):
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue

        messages: list[dict[str, Any]] = list(data.get("messages") or [])
        meta = dict(data.get("meta") or {})
        title = str(meta.get("title") or "").strip() or _derive_session_title(messages)
        last = messages[-1] if messages else {}
        items.append(
            {
                "session_id": data.get("session_id") or path.stem,
                "title": title,
                "student_id": data.get("student_id") or "",
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "message_count": len(messages),
                "preview": str(last.get("content") or "")[:80],
            }
        )

    items.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    if limit > 0:
        items = items[:limit]
    return items


__all__ = [
    "DEFAULT_SESSIONS_DIR",
    "SessionManager",
    "VALID_MESSAGE_ROLES",
    "build_message",
    "empty_session",
    "get_session_path",
    "list_sessions",
    "load_session",
    "sanitize_session_id",
    "save_session",
]
