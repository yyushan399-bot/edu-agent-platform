import type { Group, Project, ProjectNode, Submission, User } from "../api/client";

/** API 返回的时间若无时区后缀，视为 UTC 存储（与后端 SQLite 一致） */
export function parseApiDateTime(iso?: string): Date | null {
  if (!iso) return null;
  const trimmed = iso.trim();
  if (!trimmed) return null;
  const hasTz = /[Zz]$|[+-]\d{2}:\d{2}$/.test(trimmed);
  const normalized = hasTz ? trimmed : `${trimmed.replace(/\.\d+$/, "")}Z`;
  const d = new Date(normalized);
  return Number.isNaN(d.getTime()) ? null : d;
}

const DATE_TIME_FMT: Intl.DateTimeFormatOptions = {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
};

export function formatDeadline(iso?: string): string {
  const d = parseApiDateTime(iso);
  if (!d) return "未设置";
  return d.toLocaleString("zh-CN", DATE_TIME_FMT);
}

export function formatDateTime(iso?: string): string {
  const d = parseApiDateTime(iso);
  if (!d) return "未设置";
  return d.toLocaleString("zh-CN", DATE_TIME_FMT);
}

export function isPastDeadline(iso?: string): boolean {
  const d = parseApiDateTime(iso);
  if (!d) return false;
  return Date.now() > d.getTime();
}

export function fileNameFromPath(path?: string): string {
  if (!path) return "";
  return path.split(/[/\\]/).pop() || path;
}

export function getFileIconClass(name: string): string {
  const lower = name.toLowerCase();
  if (lower.endsWith(".pdf")) return "fa-solid fa-file-pdf text-red-500";
  if (lower.endsWith(".doc") || lower.endsWith(".docx"))
    return "fa-solid fa-file-word text-blue-500";
  return "fa-solid fa-file-lines text-slate-500";
}

export function findUserGroup(groups: Group[], userId: number): Group | undefined {
  return groups.find(
    (g) =>
      g.leader_id === userId || g.members.some((m) => m.user_id === userId)
  );
}

export function findUserGroupForProject(
  groups: Group[],
  userId: number,
  projectId: number
): Group | undefined {
  return groups.find(
    (g) =>
      g.project_id === projectId &&
      (g.leader_id === userId || g.members.some((m) => m.user_id === userId))
  );
}

export function resolveMemberUser(
  memberUserId: number,
  members: Group["members"],
  users: User[]
): User | undefined {
  const nested = members.find((m) => m.user_id === memberUserId)?.user;
  if (nested) return nested;
  return users.find((u) => u.id === memberUserId);
}

export function sortNodes(nodes: ProjectNode[]): ProjectNode[] {
  return [...nodes].sort((a, b) => a.order - b.order || a.id - b.id);
}

export const FINAL_REPORT_TAG = "[最终项目报告]";

export function lastProjectNodeId(nodes: ProjectNode[] | undefined): number | undefined {
  const sorted = sortNodes(nodes ?? []);
  return sorted[sorted.length - 1]?.id;
}

/** 判断是否为组长提交的小组最终项目报告（含标记文本或末节点文件上传）。 */
export function isFinalReportSubmission(
  sub: Submission,
  options?: { lastNodeId?: number }
): boolean {
  const text = sub.text_content ?? "";
  if (text.includes(FINAL_REPORT_TAG)) return true;
  const lastNodeId = options?.lastNodeId;
  if (lastNodeId != null && sub.node_id === lastNodeId && Boolean(sub.file_path)) {
    return true;
  }
  return false;
}

export function submissionsForNode(
  submissions: Submission[],
  nodeId: number,
  userId?: number
): Submission[] {
  return submissions.filter(
    (s) =>
      s.node_id === nodeId && (userId === undefined || s.user_id === userId)
  );
}

export function memberProgress(
  memberId: number,
  nodeIds: number[],
  submissions: Submission[]
): number {
  if (nodeIds.length === 0) return 0;
  const done = nodeIds.filter((nid) =>
    submissions.some((s) => s.user_id === memberId && s.node_id === nid)
  ).length;
  return Math.round((done / nodeIds.length) * 100);
}

export async function loadGroupProject(
  group: Group | undefined,
  getProject: (id: number) => Promise<{ data: Project }>,
  listProjects: () => Promise<{ data: Project[] }>
): Promise<Project | null> {
  if (group?.project_id) {
    const { data } = await getProject(group.project_id);
    return data;
  }
  const { data: projects } = await listProjects();
  return projects[0] ?? null;
}
