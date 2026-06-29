/** 组员/组长共用：AI 作业分析 + 小组项目评价 + 个人终结性评价 */
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../api/auth";
import { getEduHealth, type EduHealth } from "../../api/eduAgent";
import { eduPblSessionStorageKey, eduSectionSessionStorageKey, eduSessionStorageKey, resolveEduSessionId, resolveEduPblSessionId, resolveEduSectionSessionId } from "../../utils/eduSession";
import AiAnalyzePanel from "./AiAnalyzePanel";
import GroupEvaluationPanel from "./GroupEvaluationPanel";
import SectionEvaluationPanel from "./SectionEvaluationPanel";

type AiTab = "analyze" | "pbl" | "section";

function aiTabStorageKey(studentId: string) {
  return `student-ai-tab-${studentId}`;
}

function readStoredAiTab(studentId: string): AiTab {
  if (!studentId) return "analyze";
  const saved = sessionStorage.getItem(aiTabStorageKey(studentId));
  if (saved === "analyze" || saved === "pbl" || saved === "section") return saved;
  return "analyze";
}

interface Props {
  /** 不传则根据登录用户角色推断 */
  role?: "group_leader" | "group_member";
  /** 当前项目 ID（组长 PBL 可见性规则） */
  projectId?: number;
  /** 项目截止时间（截止后禁止上传 AI 评价报告） */
  projectDeadline?: string;
}

export default function StudentAiWorkspace({ role: roleProp, projectId, projectDeadline }: Props) {
  const { user } = useAuth();
  const role =
    roleProp ??
    (user?.role === "group_leader" ? "group_leader" : "group_member");

  const tabs = useMemo(() => {
    const all: { id: AiTab; label: string; icon: string }[] = [
      { id: "analyze", label: "AI 作业分析", icon: "fa-wand-magic-sparkles" },
      { id: "pbl", label: "小组项目评价", icon: "fa-people-group" },
      { id: "section", label: "个人终结性评价", icon: "fa-book-open" },
    ];
    if (role === "group_member") {
      return all.filter((t) => t.id !== "pbl");
    }
    return all;
  }, [role]);

  const studentId = user?.student_id ?? "";
  const sessionStorageKey = studentId ? eduSessionStorageKey(studentId) : "";
  const pblSessionStorageKey = studentId ? eduPblSessionStorageKey(studentId) : "";
  const sectionSessionStorageKey = studentId ? eduSectionSessionStorageKey(studentId) : "";

  const [aiTab, setAiTab] = useState<AiTab>(() => readStoredAiTab(studentId));
  const [health, setHealth] = useState<EduHealth | null>(null);
  const [healthError, setHealthError] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [pblSessionId, setPblSessionId] = useState("");
  const [sectionSessionId, setSectionSessionId] = useState("");

  useEffect(() => {
    if (studentId) sessionStorage.setItem(aiTabStorageKey(studentId), aiTab);
  }, [aiTab, studentId]);

  useEffect(() => {
    if (!tabs.some((t) => t.id === aiTab)) {
      setAiTab(tabs[0]?.id ?? "analyze");
    }
  }, [tabs, aiTab]);

  useEffect(() => {
    getEduHealth()
      .then(setHealth)
      .catch(() => setHealthError("AI 后端未就绪（请确认 8391 端口后端已启动）"));
  }, []);

  const persistSessionId = (id: string) => {
    setSessionId(id);
    if (sessionStorageKey) localStorage.setItem(sessionStorageKey, id);
  };

  const persistPblSessionId = (id: string) => {
    setPblSessionId(id);
    if (pblSessionStorageKey) localStorage.setItem(pblSessionStorageKey, id);
  };

  const persistSectionSessionId = (id: string) => {
    setSectionSessionId(id);
    if (sectionSessionStorageKey) localStorage.setItem(sectionSessionStorageKey, id);
  };

  useEffect(() => {
    if (!studentId) return;
    let cancelled = false;

    const ensureSession = async () => {
      try {
        const id = await resolveEduSessionId(studentId, sessionId);
        if (!cancelled && id) setSessionId(id);
      } catch {
        /* 无会话时 AI 分析仍可运行，只是不会写入聊天记录 */
      }
    };

    void ensureSession();
    return () => {
      cancelled = true;
    };
  }, [studentId]);

  useEffect(() => {
    if (!studentId || role !== "group_leader") return;
    let cancelled = false;

    const ensurePblSession = async () => {
      try {
        const id = await resolveEduPblSessionId(studentId, "");
        if (!cancelled && id) setPblSessionId(id);
      } catch {
        /* PBL 评价可独立运行 */
      }
    };

    void ensurePblSession();
    return () => {
      cancelled = true;
    };
  }, [studentId, role]);

  useEffect(() => {
    if (!studentId) return;
    let cancelled = false;

    const ensureSectionSession = async () => {
      try {
        const id = await resolveEduSectionSessionId(studentId, "");
        if (!cancelled && id) setSectionSessionId(id);
      } catch {
        /* 终结性评价可独立运行 */
      }
    };

    void ensureSectionSession();
    return () => {
      cancelled = true;
    };
  }, [studentId]);

  const llmConfigured = health?.llm_configured !== false;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 p-1 bg-slate-200 rounded-lg w-fit">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setAiTab(t.id)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors flex items-center gap-2 ${
              aiTab === t.id
                ? "bg-white text-blue-900 shadow-sm"
                : "text-slate-600 hover:text-slate-800"
            }`}
          >
            <i className={`fa-solid ${t.icon}`} />
            {t.label}
          </button>
        ))}
      </div>

      {healthError && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-lg px-4 py-3 text-sm">
          <i className="fa-solid fa-triangle-exclamation mr-2" />
          {healthError}
          <p className="text-xs mt-1 text-amber-700">
            在项目根目录启动：
            <code className="bg-amber-100 px-1 rounded ml-1">
              python -m uvicorn backend.main:app --reload --port 8391
            </code>
          </p>
        </div>
      )}

      {health && !health.llm_configured && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          未配置 LLM API Key。请在项目根目录 <code>.env</code> 中设置 DeepSeek（示例）后重启后端：
          <pre className="mt-2 text-xs bg-red-100/60 p-2 rounded overflow-x-auto">
{`OPENAI_API_KEY=你的DeepSeek密钥
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat`}
          </pre>
          <p className="text-xs mt-1 text-red-600">也兼容 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 变量名。</p>
        </div>
      )}

      <div className={aiTab === "analyze" ? "" : "hidden"}>
        <AiAnalyzePanel
          studentId={studentId}
          sessionId={sessionId}
          onSessionIdChange={persistSessionId}
          llmConfigured={llmConfigured}
          projectId={projectId}
        />
      </div>
      {role === "group_leader" && (
        <div className={aiTab === "pbl" ? "" : "hidden"}>
          <GroupEvaluationPanel
            studentId={studentId}
            sessionId={pblSessionId}
            onSessionIdChange={persistPblSessionId}
            llmConfigured={llmConfigured}
            projectId={projectId}
            projectDeadline={projectDeadline}
          />
        </div>
      )}
      <div className={aiTab === "section" ? "" : "hidden"}>
        <SectionEvaluationPanel
          studentId={studentId}
          sessionId={sectionSessionId}
          onSessionIdChange={persistSectionSessionId}
          llmConfigured={llmConfigured}
          projectDeadline={projectDeadline}
        />
      </div>
    </div>
  );
}
