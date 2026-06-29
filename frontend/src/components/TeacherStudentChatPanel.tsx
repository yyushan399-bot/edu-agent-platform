/** 教师端：学生列表 + AI 聊天记录查看 */
import { useCallback, useEffect, useState } from "react";
import type { ChatMessage, User } from "../api/client";
import { teacherChatApi } from "../api/client";

interface Props {
  students: User[];
}

function roleLabel(role: User["role"]) {
  if (role === "group_leader") return "组长";
  return "组员";
}

function formatTime(iso: string) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function isUserMessage(role: string) {
  return role === "user" || role === "student";
}

export default function TeacherStudentChatPanel({ students }: Props) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionCount, setSessionCount] = useState(0);
  const [emptySessionCount, setEmptySessionCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");

  const sortedStudents = [...students].sort((a, b) =>
    a.name.localeCompare(b.name, "zh-CN")
  );

  const filteredStudents = sortedStudents.filter((s) => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (
      s.name.toLowerCase().includes(q) ||
      s.student_id.toLowerCase().includes(q)
    );
  });

  const selectedStudent = sortedStudents.find((s) => s.id === selectedId) ?? null;

  const loadMessages = useCallback(async (student: User) => {
    setLoading(true);
    setError("");
    try {
      const { data } = await teacherChatApi.getStudentMessages(student.student_id);
      setMessages(data.messages);
      setSessionCount(data.session_count);
      setEmptySessionCount(data.empty_session_count ?? 0);
    } catch (err: unknown) {
      setMessages([]);
      setSessionCount(0);
      setEmptySessionCount(0);
      const ax = err as {
        response?: { status?: number; data?: { detail?: string } };
        message?: string;
      };
      const detail = ax.response?.data?.detail;
      if (detail) {
        setError(detail);
      } else if (ax.response?.status === 401 || ax.response?.status === 403) {
        setError("登录已过期或无权限，请重新登录。");
      } else {
        setError(
          ax.message ||
            "加载失败。请确认项目化学习系统后端（端口 8391）已启动，并已用教师账号登录。"
        );
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedStudent) {
      void loadMessages(selectedStudent);
    } else {
      setMessages([]);
      setSessionCount(0);
      setEmptySessionCount(0);
      setError("");
    }
  }, [selectedStudent, loadMessages]);

  useEffect(() => {
    if (!selectedId && sortedStudents.length > 0) {
      setSelectedId(sortedStudents[0].id);
    }
  }, [selectedId, sortedStudents]);

  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
      <div className="px-6 py-4 border-b border-slate-100 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-blue-900 border-l-4 border-blue-900 pl-3">
            <i className="fa-solid fa-user-graduate mr-2" />
            学生管理 · AI 对话记录
          </h2>
          <p className="text-xs text-slate-400 mt-2 ml-7">
            查看学生与 AI 智能体的历史对话（学生使用「AI 智能评价」后自动保存）
          </p>
        </div>
        <div className="relative">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索姓名或学号"
            className="pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-sm outline-none focus:border-blue-500 w-56"
          />
          <i className="fa-solid fa-magnifying-glass absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-xs" />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[280px_1fr] min-h-[520px]">
        <div className="border-r border-slate-100 bg-slate-50/80 max-h-[560px] overflow-y-auto">
          {filteredStudents.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-12">暂无学生账号</p>
          ) : (
            filteredStudents.map((student) => {
              const active = student.id === selectedId;
              return (
                <button
                  key={student.id}
                  type="button"
                  onClick={() => setSelectedId(student.id)}
                  className={`w-full text-left px-4 py-3 border-b border-slate-100 transition-colors ${
                    active
                      ? "bg-white border-l-4 border-l-indigo-600 shadow-sm"
                      : "hover:bg-white/80 border-l-4 border-l-transparent"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-slate-800 truncate">
                      {student.name}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-200 text-slate-600 shrink-0">
                      {roleLabel(student.role)}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-1 font-mono">
                    {student.student_id}
                  </p>
                </button>
              );
            })
          )}
        </div>

        <div className="flex flex-col min-h-[520px]">
          {selectedStudent ? (
            <>
              <div className="px-5 py-3 border-b border-slate-100 bg-white flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-semibold text-slate-800">{selectedStudent.name}</p>
                  <p className="text-xs text-slate-400">
                    学号 {selectedStudent.student_id}
                    {sessionCount > 0 && (
                      <span className="ml-2">· {sessionCount} 个会话</span>
                    )}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void loadMessages(selectedStudent)}
                  disabled={loading}
                  className="text-xs text-indigo-600 hover:text-indigo-800 disabled:opacity-50"
                >
                  <i className="fa-solid fa-rotate-right mr-1" />
                  刷新
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-[#f7f8fb]">
                {loading ? (
                  <p className="text-center text-slate-400 text-sm py-16">加载对话中...</p>
                ) : error ? (
                  <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-lg px-4 py-3 text-sm whitespace-pre-wrap">
                    {error}
                  </div>
                ) : messages.length === 0 ? (
                  <div className="text-center py-16 text-slate-400">
                    <i className="fa-solid fa-comments text-4xl mb-3 opacity-40" />
                    <p className="text-sm">该学生暂无 AI 对话记录</p>
                    {emptySessionCount > 0 ? (
                      <p className="text-xs mt-2 text-amber-600">
                        检测到 {emptySessionCount} 个空会话（评价时未写入消息）。
                        请让学生重新提交一次 AI 评价，对话将同步至此。
                      </p>
                    ) : (
                      <p className="text-xs mt-2">
                        学生使用「AI 智能评价」功能后，对话将自动保存至此
                      </p>
                    )}
                  </div>
                ) : (
                  messages.map((msg) => {
                    const fromUser = isUserMessage(msg.role);
                    return (
                      <div
                        key={msg.message_id}
                        className={`flex ${fromUser ? "justify-end" : "justify-start"}`}
                      >
                        <div
                          className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                            fromUser
                              ? "bg-indigo-600 text-white rounded-br-md"
                              : "bg-white text-slate-700 border border-slate-200 rounded-bl-md"
                          }`}
                        >
                          {!fromUser && (
                            <p className="text-[10px] font-semibold text-indigo-600 mb-1">
                              <i className="fa-solid fa-robot mr-1" />
                              AI 智能体
                            </p>
                          )}
                          <p className="whitespace-pre-wrap break-words">{msg.content}</p>
                          <p
                            className={`text-[10px] mt-2 ${
                              fromUser ? "text-indigo-200" : "text-slate-400"
                            }`}
                          >
                            {formatTime(msg.timestamp)}
                            {msg.session_title && (
                              <span className="ml-2 opacity-80">· {msg.session_title}</span>
                            )}
                          </p>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
              请从左侧选择一名学生
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
