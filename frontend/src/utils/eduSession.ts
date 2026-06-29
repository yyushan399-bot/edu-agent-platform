/** 学生 AI 会话：避免重复创建、提交前确保 session_id 可用 */
import { createEduSession } from "../api/eduAgent";

const pendingCreates = new Map<string, Promise<string>>();

export function eduSessionStorageKey(studentId: string) {
  return `edu_session_${studentId}`;
}

export function eduPblSessionStorageKey(studentId: string) {
  return `edu_session_pbl_${studentId}`;
}

export function eduSectionSessionStorageKey(studentId: string) {
  return `edu_session_section_${studentId}`;
}

/** 个人终结性评价专用会话，与 AI 作业分析隔离 */
export async function resolveEduSectionSessionId(
  studentId: string,
  currentSessionId = "",
): Promise<string> {
  const sid = studentId.trim();
  if (!sid) return "";
  if (currentSessionId) return currentSessionId;

  const storageKey = eduSectionSessionStorageKey(sid);
  const cached = localStorage.getItem(storageKey);
  if (cached) return cached;

  const pendingKey = `${storageKey}:pending`;
  let pending = pendingCreates.get(pendingKey);
  if (!pending) {
    pending = createEduSession(sid, "个人终结性评价").then((session) => {
      localStorage.setItem(storageKey, session.session_id);
      pendingCreates.delete(pendingKey);
      return session.session_id;
    });
    pendingCreates.set(pendingKey, pending);
  }
  return pending;
}

/** 小组项目评价专用会话，与 AI 作业分析隔离 */
export async function resolveEduPblSessionId(
  studentId: string,
  currentSessionId = "",
): Promise<string> {
  const sid = studentId.trim();
  if (!sid) return "";
  if (currentSessionId) return currentSessionId;

  const storageKey = eduPblSessionStorageKey(sid);
  const cached = localStorage.getItem(storageKey);
  if (cached) return cached;

  const pendingKey = `${storageKey}:pending`;
  let pending = pendingCreates.get(pendingKey);
  if (!pending) {
    pending = createEduSession(sid, "小组项目评价").then((session) => {
      localStorage.setItem(storageKey, session.session_id);
      pendingCreates.delete(pendingKey);
      return session.session_id;
    });
    pendingCreates.set(pendingKey, pending);
  }
  return pending;
}

/** 初始化或读取当前会话（React StrictMode 下也不会重复创建） */
export async function resolveEduSessionId(
  studentId: string,
  currentSessionId = "",
): Promise<string> {
  const sid = studentId.trim();
  if (!sid) return "";
  if (currentSessionId) return currentSessionId;

  const storageKey = eduSessionStorageKey(sid);
  const cached = localStorage.getItem(storageKey);
  if (cached) return cached;

  let pending = pendingCreates.get(storageKey);
  if (!pending) {
    pending = createEduSession(sid, "AI 形成性评价").then((session) => {
      localStorage.setItem(storageKey, session.session_id);
      pendingCreates.delete(storageKey);
      return session.session_id;
    });
    pendingCreates.set(storageKey, pending);
  }
  return pending;
}

/** 新对话：强制创建新 session 并写入 localStorage */
export async function startNewEduSession(studentId: string): Promise<string> {
  const sid = studentId.trim();
  if (!sid) return "";
  const storageKey = eduSessionStorageKey(sid);
  pendingCreates.delete(storageKey);
  const session = await createEduSession(sid, "AI 形成性评价");
  localStorage.setItem(storageKey, session.session_id);
  return session.session_id;
}
