/** 组长小组项目评价：跨 Tab 切换保持进行中的任务与结果 */
import { formatEduAxiosError, postGroupEvaluation } from "../api/eduAgent";
import { resolveEduPblSessionId } from "./eduSession";

export type PblLoadingPhase = "idle" | "scoring" | "reviewing";

export interface GroupPblJobSnapshot {
  fileName: string;
  loading: boolean;
  phase: PblLoadingPhase;
  scorePreview: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  error: string;
}

const STORAGE_PREFIX = "group-pbl-job:";

function storageKey(jobKey: string) {
  return `${STORAGE_PREFIX}${jobKey}`;
}

function emptySnapshot(): GroupPblJobSnapshot {
  return {
    fileName: "",
    loading: false,
    phase: "idle",
    scorePreview: null,
    result: null,
    error: "",
  };
}

const jobs = new Map<string, GroupPblJobSnapshot>();
const listeners = new Map<string, Set<() => void>>();
const running = new Map<string, Promise<void>>();

export function groupPblJobKey(studentId: string, projectId?: number) {
  return `${studentId}:${projectId ?? "none"}`;
}

function persist(jobKey: string, snap: GroupPblJobSnapshot) {
  const payload = {
    fileName: snap.fileName,
    loading: snap.loading,
    phase: snap.phase,
    scorePreview: snap.scorePreview,
    result: snap.result,
    error: snap.error,
  };
  try {
    sessionStorage.setItem(storageKey(jobKey), JSON.stringify(payload));
  } catch {
    /* quota */
  }
}

function loadPersisted(jobKey: string): GroupPblJobSnapshot {
  try {
    const raw = sessionStorage.getItem(storageKey(jobKey));
    if (!raw) return emptySnapshot();
    const data = JSON.parse(raw) as Partial<GroupPblJobSnapshot>;
    return {
      fileName: data.fileName ?? "",
      loading: false,
      phase: "idle",
      scorePreview: data.scorePreview ?? null,
      result: data.result ?? null,
      error: data.error ?? "",
    };
  } catch {
    return emptySnapshot();
  }
}

function notify(jobKey: string) {
  listeners.get(jobKey)?.forEach((cb) => cb());
}

function patch(jobKey: string, partial: Partial<GroupPblJobSnapshot>) {
  const prev = jobs.get(jobKey) ?? loadPersisted(jobKey);
  const next = { ...prev, ...partial };
  jobs.set(jobKey, next);
  persist(jobKey, next);
  notify(jobKey);
}

export function getGroupPblJob(jobKey: string): GroupPblJobSnapshot {
  if (!jobs.has(jobKey)) {
    jobs.set(jobKey, loadPersisted(jobKey));
  }
  return jobs.get(jobKey)!;
}

export function subscribeGroupPblJob(jobKey: string, cb: () => void) {
  let set = listeners.get(jobKey);
  if (!set) {
    set = new Set();
    listeners.set(jobKey, set);
  }
  set.add(cb);
  return () => {
    set!.delete(cb);
  };
}

export function setGroupPblJobError(jobKey: string, error: string) {
  patch(jobKey, { error, loading: false, phase: "idle" });
}

export function setGroupPblFileName(jobKey: string, fileName: string) {
  patch(jobKey, { fileName });
}

export function clearGroupPblJob(jobKey: string) {
  jobs.set(jobKey, emptySnapshot());
  sessionStorage.removeItem(storageKey(jobKey));
  notify(jobKey);
}

export function isGroupPblRunning(jobKey: string) {
  return running.has(jobKey);
}

/** 从服务端刷新组长可见的最新评价（解决截止+30 天后仍显示缓存遮挡的问题） */
export async function refreshLeaderPblFromServer(
  jobKey: string,
  projectId: number
): Promise<boolean> {
  const { groupPblApi } = await import("../api/client");
  try {
    const { data } = await groupPblApi.getMyLatest(projectId);
    if (!data.has_evaluation) return false;
    const snap = getGroupPblJob(jobKey);
    patch(jobKey, {
      fileName: snap.fileName || String(data.filename || ""),
      result: data as Record<string, unknown>,
      loading: false,
      phase: "idle",
    });
    return data.scores_visible !== false;
  } catch {
    return false;
  }
}

export async function runGroupPblEvaluation(params: {
  jobKey: string;
  file: File;
  studentId: string;
  sessionId?: string;
  projectId?: number;
  onSessionIdChange?: (sessionId: string) => void;
}): Promise<void> {
  const { jobKey, file, studentId, sessionId, projectId, onSessionIdChange } = params;

  if (running.has(jobKey)) {
    return running.get(jobKey)!;
  }

  const task = (async () => {
    patch(jobKey, {
      fileName: file.name,
      loading: true,
      phase: "scoring",
      error: "",
      scorePreview: null,
      result: null,
    });

    const reviewPhaseTimer = window.setTimeout(() => {
      if (running.has(jobKey)) {
        patch(jobKey, { phase: "reviewing" });
      }
    }, 25000);

    try {
      const activeSessionId = await resolveEduPblSessionId(studentId, sessionId ?? "");
      if (activeSessionId && activeSessionId !== sessionId) {
        onSessionIdChange?.(activeSessionId);
      }

      const finalResult = (await postGroupEvaluation({
        file,
        studentId,
        sessionId: activeSessionId,
        projectId,
        enableReview: true,
        scoringTimes: 10,
      })) as Record<string, unknown>;

      patch(jobKey, {
        scorePreview: finalResult,
        result: finalResult,
        loading: false,
        phase: "idle",
      });
    } catch (err) {
      patch(jobKey, {
        loading: false,
        phase: "idle",
        error: formatEduAxiosError(err),
      });
    } finally {
      window.clearTimeout(reviewPhaseTimer);
      running.delete(jobKey);
    }
  })();

  running.set(jobKey, task);
  return task;
}
