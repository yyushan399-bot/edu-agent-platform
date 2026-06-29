/** 教育智能体 LangGraph API（合并至 8391，经 Vite 代理 /api → /edu-health 等） */
import axios, { type AxiosError } from "axios";

const LONG_TIMEOUT = 30 * 60 * 1000;

const eduClient = axios.create({
  baseURL: "/api",
  timeout: LONG_TIMEOUT,
});

eduClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export interface EduHealth {
  status?: string;
  llm_configured?: boolean;
  rag_enabled?: boolean;
  deep_research_available?: boolean;
  evaluation_modes?: string[];
}

export function formatEduAxiosError(err: unknown): string {
  const e = err as AxiosError<{ detail?: string }>;
  if (e.code === "ECONNABORTED") {
    return "分析超时。首次运行可能需下载模型，请查看 LangGraph 后端终端是否仍在运行。";
  }
  if (e.code === "ERR_NETWORK" || e.message === "Network Error") {
    return (
      "无法连接 AI 后端。请确认 8391 后端已启动：\n" +
      "python -m uvicorn backend.main:app --reload --port 8391"
    );
  }
  const detail = e.response?.data?.detail;
  if (typeof detail === "string") return detail;
  return e.message || "未知错误";
}

export async function getEduHealth(): Promise<EduHealth> {
  const { data } = await eduClient.get<EduHealth>("/edu-health");
  return data;
}

export async function postAnalyze(payload: {
  files?: File[];
  text?: string;
  studentId?: string;
  sessionId?: string;
  routes?: string;
  selfScore?: number;
  projectId?: number;
  enableDeepResearch?: boolean;
}) {
  const form = new FormData();
  for (const file of payload.files || []) {
    form.append("files", file);
  }
  if (payload.text?.trim()) form.append("text", payload.text.trim());
  if (payload.studentId?.trim()) form.append("student_id", payload.studentId.trim());
  if (payload.routes?.trim()) form.append("routes", payload.routes.trim());
  if (payload.sessionId?.trim()) form.append("session_id", payload.sessionId.trim());
  if (payload.selfScore != null && !Number.isNaN(payload.selfScore)) {
    form.append("self_score", String(payload.selfScore));
  }
  if (payload.projectId != null && !Number.isNaN(payload.projectId)) {
    form.append("project_id", String(payload.projectId));
  }
  form.append("enable_deep_research", payload.enableDeepResearch ? "true" : "false");
  const { data } = await eduClient.post("/analyze", form);
  return data;
}

export async function postGroupEvaluation(payload: {
  file: File;
  enableReview?: boolean;
  reviewRounds?: number;
  scoringTimes?: number;
  studentId?: string;
  sessionId?: string;
  projectId?: number;
}) {
  const form = new FormData();
  form.append("file", payload.file);
  form.append("enable_review", payload.enableReview ? "true" : "false");
  if (payload.reviewRounds != null) form.append("review_rounds", String(payload.reviewRounds));
  if (payload.scoringTimes != null) form.append("scoring_times", String(payload.scoringTimes));
  if (payload.studentId?.trim()) form.append("student_id", payload.studentId.trim());
  if (payload.sessionId?.trim()) form.append("session_id", payload.sessionId.trim());
  if (payload.projectId != null) form.append("project_id", String(payload.projectId));
  const { data } = await eduClient.post("/group-evaluation", form);
  return data;
}

export async function postSectionEvaluation(payload: {
  file: File;
  sectionName?: string;
  enableReview?: boolean;
  reviewRounds?: number;
  scoringTimes?: number;
  cvThreshold?: number;
  studentId?: string;
  sessionId?: string;
}) {
  const form = new FormData();
  form.append("file", payload.file);
  if (payload.sectionName?.trim()) form.append("section_name", payload.sectionName.trim());
  form.append("enable_review", payload.enableReview ? "true" : "false");
  if (payload.reviewRounds != null) form.append("review_rounds", String(payload.reviewRounds));
  if (payload.scoringTimes != null) form.append("scoring_times", String(payload.scoringTimes));
  if (payload.cvThreshold != null) form.append("cv_threshold", String(payload.cvThreshold));
  if (payload.studentId?.trim()) form.append("student_id", payload.studentId.trim());
  if (payload.sessionId?.trim()) form.append("session_id", payload.sessionId.trim());
  const { data } = await eduClient.post("/section-evaluation", form);
  return data;
}

export function formatScore(value: unknown): string {
  if (value == null || value === "") return "—";
  const num = Number(value);
  return Number.isNaN(num) ? String(value) : num.toFixed(2);
}

export interface ChatSessionSummary {
  session_id: string;
  title: string;
  student_id: string;
  created_at?: string;
  updated_at?: string;
  message_count: number;
  preview?: string;
}

export interface ChatMessage {
  message_id: string;
  role: string;
  content: string;
  timestamp: string;
  session_id?: string;
  session_title?: string;
  meta?: Record<string, unknown>;
}

export async function getEduSessionMessages(sessionId: string) {
  const { data } = await eduClient.get<{
    success: boolean;
    messages: ChatMessage[];
  }>(`/sessions/${encodeURIComponent(sessionId)}`);
  return data.messages;
}

export async function createEduSession(studentId: string, title = "AI 作业分析对话") {
  const { data } = await eduClient.post<{ success: boolean; session: ChatSessionSummary }>(
    "/sessions",
    { student_id: studentId, title }
  );
  return data.session;
}

export async function listEduSessions(studentId?: string) {
  const { data } = await eduClient.get<{ success: boolean; sessions: ChatSessionSummary[] }>(
    "/sessions",
    { params: studentId ? { student_id: studentId, limit: 200 } : { limit: 200 } }
  );
  return data.sessions;
}

export async function getStudentChatMessages(studentId: string, limit = 300) {
  const { data } = await eduClient.get<{
    success: boolean;
    student_id: string;
    session_count: number;
    message_count: number;
    messages: ChatMessage[];
  }>(`/sessions/by-student/${encodeURIComponent(studentId)}/messages`, {
    params: { limit },
  });
  return data;
}
