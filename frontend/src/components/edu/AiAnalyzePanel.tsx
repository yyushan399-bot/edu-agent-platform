import { useCallback, useEffect, useRef, useState } from "react";
import {
  type ChatMessage,
  formatEduAxiosError,
  formatScore,
  getEduSessionMessages,
  postAnalyze,
} from "../../api/eduAgent";
import { resolveEduSessionId, startNewEduSession } from "../../utils/eduSession";
import EduChatHistory from "./EduChatHistory";
import FileDropZone from "./FileDropZone";

interface Props {
  studentId: string;
  sessionId: string;
  onSessionIdChange: (sessionId: string) => void;
  llmConfigured: boolean;
  projectId?: number;
}

const MIN_SELF_COMMENT_LEN = 30;

const ROUTE_OPTIONS = [
  { id: "theory", label: "理论部分", icon: "fa-book" },
  { id: "literature", label: "文献部分", icon: "fa-book-open" },
  { id: "practice", label: "实践部分", icon: "fa-flask" },
  { id: "data", label: "数据部分", icon: "fa-chart-column" },
] as const;

function buildSelfEvalPayload(selfScore: number, selfComment: string): string {
  const lines = [`【自评 ${selfScore} / 5 分】`];
  const comment = selfComment.trim();
  if (comment) lines.push(comment);
  return lines.join("\n");
}

export default function AiAnalyzePanel({
  studentId,
  sessionId,
  onSessionIdChange,
  llmConfigured,
  projectId,
}: Props) {
  const [files, setFiles] = useState<File[]>([]);
  const [selfComment, setSelfComment] = useState("");
  const [selectedRoutes, setSelectedRoutes] = useState<string[]>([]);
  const [selfScore, setSelfScore] = useState(3);
  const [deepResearch, setDeepResearch] = useState(false);
  const [loading, setLoading] = useState(false);
  const [creatingSession, setCreatingSession] = useState(false);
  const [error, setError] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const selfCommentLen = selfComment.trim().length;

  const toggleRoute = (routeId: string) => {
    setSelectedRoutes((prev) =>
      prev.includes(routeId) ? prev.filter((r) => r !== routeId) : [...prev, routeId]
    );
  };

  const loadMessages = useCallback(async (sid: string) => {
    if (!sid) {
      setMessages([]);
      return;
    }
    setMessagesLoading(true);
    try {
      const list = await getEduSessionMessages(sid);
      setMessages(list);
    } catch {
      setMessages([]);
    } finally {
      setMessagesLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMessages(sessionId);
  }, [sessionId, loadMessages]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleNewSession = async () => {
    if (!studentId) return;
    setCreatingSession(true);
    setError("");
    try {
      const newSessionId = await startNewEduSession(studentId);
      onSessionIdChange(newSessionId);
      setFiles([]);
      setSelfComment("");
      setSelfScore(3);
      setSelectedRoutes([]);
      setMessages([]);
    } catch (err) {
      setError(formatEduAxiosError(err));
    } finally {
      setCreatingSession(false);
    }
  };

  const handleSubmit = async () => {
    if (!files.length) {
      setError("请上传作业文件（PDF / Word / 图片）");
      return;
    }
    if (selfCommentLen < MIN_SELF_COMMENT_LEN) {
      setError(`自评说明不少于 ${MIN_SELF_COMMENT_LEN} 字（当前 ${selfCommentLen} 字）`);
      return;
    }
    if (!llmConfigured) {
      setError("未配置 API Key");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const activeSessionId = await resolveEduSessionId(studentId, sessionId);
      if (activeSessionId !== sessionId) {
        onSessionIdChange(activeSessionId);
      }
      await postAnalyze({
        files,
        text: buildSelfEvalPayload(selfScore, selfComment),
        studentId,
        sessionId: activeSessionId,
        routes: selectedRoutes.length ? selectedRoutes.join(",") : undefined,
        selfScore,
        projectId,
        enableDeepResearch: deepResearch,
      });
      setFiles([]);
      await loadMessages(activeSessionId);
    } catch (err) {
      setError(formatEduAxiosError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl p-6 shadow-sm border border-slate-200 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-blue-900 border-l-4 border-blue-900 pl-3">
            AI 作业分析（四路由 · 形成性评价）
          </h2>
          <p className="text-sm text-slate-500 mt-2">
            上传作业并填写自评，系统按量规 1–5 分给出形成性反馈
          </p>
        </div>
        <button
          type="button"
          onClick={() => void handleNewSession()}
          disabled={creatingSession || loading || !studentId}
          className="shrink-0 px-4 py-2 text-sm font-medium border border-blue-200 text-blue-900 rounded-lg hover:bg-blue-50 disabled:opacity-50 flex items-center gap-2"
        >
          <i className="fa-solid fa-plus" />
          {creatingSession ? "创建中…" : "新对话"}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <p className="text-xs font-medium text-slate-500 mb-1.5">作业文件</p>
          <FileDropZone
            accept=".pdf,.docx,.png,.jpg,.jpeg"
            multiple
            disabled={loading}
            onFilesSelected={setFiles}
            emptyLabel="选择文件"
            selectedLabel={
              files.length > 0 ? files.map((f) => f.name).join(", ") : undefined
            }
          />
        </div>
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <p className="text-xs font-medium text-slate-500">自评</p>
            <span
              className={`text-xs tabular-nums ${
                selfCommentLen >= MIN_SELF_COMMENT_LEN ? "text-emerald-600" : "text-amber-600"
              }`}
            >
              {selfCommentLen >= MIN_SELF_COMMENT_LEN
                ? `已输入 ${selfCommentLen} 字`
                : `已输入 ${selfCommentLen} 字，至少 ${MIN_SELF_COMMENT_LEN} 字`}
            </span>
          </div>
          <textarea
            value={selfComment}
            onChange={(e) => setSelfComment(e.target.value)}
            placeholder="在此填写自评说明（不少于 30 字）"
            rows={5}
            className="w-full h-[calc(100%-1.25rem)] min-h-[140px] border border-slate-300 rounded-lg p-3 text-sm outline-none focus:border-blue-500 resize-none"
          />
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 space-y-2">
        <div className="flex items-center justify-between text-sm">
          <label htmlFor="self-score" className="font-medium text-slate-700">
            自评分数
          </label>
          <span className="text-blue-900 font-bold tabular-nums">
            {formatScore(selfScore)} / 5
          </span>
        </div>
        <input
          id="self-score"
          type="range"
          min={0}
          max={5}
          step={0.5}
          value={selfScore}
          onChange={(e) => setSelfScore(Number(e.target.value))}
          disabled={loading}
          className="w-full accent-blue-900"
        />
        <div className="flex justify-between text-xs text-slate-400">
          <span>0 未掌握</span>
          <span>3 合格</span>
          <span>5 优秀</span>
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-xs font-medium text-slate-500">指定评价维度（可选，不选则由系统自动路由）</p>
        <div className="flex flex-wrap gap-2">
          {ROUTE_OPTIONS.map(({ id, label, icon }) => {
            const active = selectedRoutes.includes(id);
            return (
              <button
                key={id}
                type="button"
                disabled={loading}
                onClick={() => toggleRoute(id)}
                className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors flex items-center gap-2 ${
                  active
                    ? "bg-blue-900 text-white border-blue-900 shadow-sm"
                    : "bg-white text-slate-600 border-slate-300 hover:border-blue-400 hover:text-blue-900"
                }`}
              >
                <i className={`fa-solid ${icon}`} />
                {label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex flex-wrap gap-4 items-center text-sm">
        <label className="flex items-center gap-2 text-slate-600 ml-auto">
          <input
            type="checkbox"
            checked={deepResearch}
            onChange={(e) => setDeepResearch(e.target.checked)}
          />
          深度联网研究（较慢）
        </label>
      </div>

      <div className="flex gap-3">
        <button
          type="button"
          onClick={() => {
            setFiles([]);
            setSelfComment("");
            setSelectedRoutes([]);
            setError("");
          }}
          disabled={loading}
          className="px-4 py-2 border border-slate-300 rounded-lg text-sm"
        >
          清空表单
        </button>
        <button
          type="button"
          onClick={() => void handleSubmit()}
          disabled={loading || !llmConfigured}
          className="px-6 py-2 bg-blue-900 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-60"
        >
          {loading ? "分析中（首次可能 10+ 分钟）…" : "提交并分析"}
        </button>
      </div>

      {error && (
        <pre className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg p-3 whitespace-pre-wrap">
          {error}
        </pre>
      )}

      <div className="border-t border-slate-200 pt-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-slate-700">
            <i className="fa-solid fa-clock-rotate-left mr-2 text-blue-900" />
            对话记录
          </h3>
          <button
            type="button"
            onClick={() => void loadMessages(sessionId)}
            disabled={messagesLoading || !sessionId}
            className="text-xs text-blue-800 hover:text-blue-600 disabled:opacity-50"
          >
            <i className="fa-solid fa-rotate-right mr-1" />
            刷新
          </button>
        </div>
        <div className="rounded-xl border border-slate-200 bg-[#f7f8fb] p-4 max-h-[420px] overflow-y-auto min-h-[200px]">
          <EduChatHistory
            messages={messages}
            loading={messagesLoading}
            emptyHint="提交作业后，您与 AI 的对话将一直显示在这里"
          />
          <div ref={chatEndRef} />
        </div>
      </div>
    </div>
  );
}
