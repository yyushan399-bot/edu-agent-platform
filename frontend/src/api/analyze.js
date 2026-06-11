import axios from "axios";

/** 开发环境走 Vite 代理 /api → 8000，避免跨域 Network Error */
const baseURL = import.meta.env.DEV
  ? "/api"
  : import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

/** 健康检查等短请求 */
const client = axios.create({
  baseURL,
  timeout: 30000,
});

/** 首次分析可能下载 BGE-M3 + 多轮 LLM，需更长等待 */
const ANALYZE_TIMEOUT_MS = 30 * 60 * 1000;

/**
 * 提交作业分析
 */
export async function postAnalyze(payload) {
  const form = new FormData();

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
  if (payload.memoryK != null) {
    form.append("memory_k", String(payload.memoryK));
  }
  if (payload.sessionId?.trim()) {
    form.append("session_id", payload.sessionId.trim());
  }
  form.append(
    "enable_deep_research",
    payload.enableDeepResearch ? "true" : "false"
  );

  const { data } = await client.post("/analyze", form, {
    timeout: ANALYZE_TIMEOUT_MS,
  });
  return data;
}

export async function getHealth() {
  const { data } = await client.get("/health");
  return data;
}

export function formatAxiosError(err) {
  if (
    err.code === "ECONNABORTED" ||
    (err.message && String(err.message).includes("timeout"))
  ) {
    return (
      "前端等待超时（首次分析需下载向量模型并调用 AI，可能超过 10 分钟）。\n" +
      "请查看 uvicorn 终端是否仍在运行；若已出现 LangGraph invoke done，可刷新页面重试提交。\n" +
      "第二次分析通常会快很多。"
    );
  }
  if (err.code === "ERR_NETWORK" || err.message === "Network Error") {
    return (
      "无法连接后端。请确认：\n" +
      "1) 后端已启动：cd backend && python -m uvicorn api.main:app --host 127.0.0.1 --port 8000\n" +
      "2) 浏览器可打开 http://127.0.0.1:8000/health\n" +
      "3) 前端用 npm run dev 启动后，开发模式会走 /api 代理"
    );
  }
  const status = err.response?.status;
  const detail = err.response?.data?.detail;
  if (typeof detail === "string") {
    return status ? `HTTP ${status}\n\n${detail}` : detail;
  }
  if (detail) return JSON.stringify(detail, null, 2);
  if (status === 500) {
    return `服务器内部错误 (500)。请查看运行 uvicorn 的终端里的红色报错。\n${err.message}`;
  }
  return err.message || "未知错误";
}
