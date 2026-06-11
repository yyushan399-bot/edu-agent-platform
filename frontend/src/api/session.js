import axios from "axios";

const baseURL = import.meta.env.DEV
  ? "/api"
  : import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

const client = axios.create({
  baseURL,
  timeout: 30000,
});

export async function listSessions(limit = 100) {
  const { data } = await client.get("/sessions", { params: { limit } });
  return data;
}

export async function createSession({ studentId, title } = {}) {
  const { data } = await client.post("/sessions", {
    student_id: studentId?.trim() || null,
    title: title || "新会话",
  });
  return data;
}

export async function getSession(sessionId) {
  const { data } = await client.get(`/sessions/${sessionId}`);
  return data;
}
