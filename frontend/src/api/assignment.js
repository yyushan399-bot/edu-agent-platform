import axios from "axios";
import { formatAxiosError } from "./analyze";

const baseURL = import.meta.env.DEV
  ? "/api"
  : import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

const ANALYZE_TIMEOUT_MS = 30 * 60 * 1000;

const client = axios.create({
  baseURL,
  timeout: ANALYZE_TIMEOUT_MS,
});

/**
 * 提交作业（含自评，写入 self_assessments + AI 评估）
 */
export async function postAssignmentSubmit(assignmentId, payload) {
  const form = new FormData();
  form.append("user_id", String(payload.userId));
  form.append("self_score", String(payload.selfScore));
  if (payload.selfComment?.trim()) {
    form.append("self_comment", payload.selfComment.trim());
  }
  for (const file of payload.files || []) {
    form.append("files", file);
  }
  if (payload.text?.trim()) {
    form.append("text", payload.text.trim());
  }
  if (payload.studentId?.trim()) {
    form.append("student_id", payload.studentId.trim());
  }
  if (payload.routes?.trim()) {
    form.append("routes", payload.routes.trim());
  }
  if (payload.sessionId?.trim()) {
    form.append("session_id", payload.sessionId.trim());
  }
  form.append(
    "enable_deep_research",
    payload.enableDeepResearch ? "true" : "false"
  );

  const { data } = await client.post(`/assignments/${assignmentId}/submit`, form);
  return data;
}

export { formatAxiosError };
