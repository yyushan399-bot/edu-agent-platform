/** 学生端 AI 对话记录展示 */
import type { ChatMessage } from "../../api/eduAgent";

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

function scoreBadge(meta?: Record<string, unknown>) {
  if (!meta) return null;
  const score = meta.rubric_score ?? meta.total_score;
  if (score == null) return null;
  const num = Number(score);
  if (Number.isNaN(num)) return null;
  const display = num > 5 ? (num / 20).toFixed(1) : num.toFixed(2);
  return (
    <span className="inline-block mt-2 text-xs bg-blue-50 text-blue-800 px-2 py-0.5 rounded">
      系统评估 {display} / 5
    </span>
  );
}

interface Props {
  messages: ChatMessage[];
  loading?: boolean;
  emptyHint?: string;
}

export default function EduChatHistory({ messages, loading, emptyHint }: Props) {
  if (loading) {
    return (
      <p className="text-center text-slate-400 text-sm py-12">加载对话记录中…</p>
    );
  }

  if (messages.length === 0) {
    return (
      <div className="text-center py-12 text-slate-400">
        <i className="fa-solid fa-comments text-3xl mb-3 opacity-40" />
        <p className="text-sm">{emptyHint || "暂无对话，提交作业后将在此显示与 AI 的记录"}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {messages.map((msg) => {
        const fromUser = isUserMessage(msg.role);
        return (
          <div
            key={msg.message_id}
            className={`flex ${fromUser ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                fromUser
                  ? "bg-blue-900 text-white rounded-br-md"
                  : "bg-white text-slate-700 border border-slate-200 rounded-bl-md"
              }`}
            >
              {!fromUser && (
                <p className="text-[10px] font-semibold text-blue-700 mb-1">
                  <i className="fa-solid fa-robot mr-1" />
                  AI 形成性评价
                </p>
              )}
              {fromUser && (
                <p className="text-[10px] font-semibold text-blue-200 mb-1">我</p>
              )}
              <p className="whitespace-pre-wrap break-words">{msg.content}</p>
              {!fromUser && scoreBadge(msg.meta)}
              <p
                className={`text-[10px] mt-2 ${
                  fromUser ? "text-blue-200" : "text-slate-400"
                }`}
              >
                {formatTime(msg.timestamp)}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
