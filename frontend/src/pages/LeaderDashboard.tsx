/** 组长端 —— 组员分工 + 时间轴成果提交 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../api/auth";
import {
  groupsApi,
  projectsApi,
  submissionsApi,
  type Group,
  type ProjectNode,
  type Submission,
} from "../api/client";
import {
  fileNameFromPath,
  formatDeadline,
  getFileIconClass,
  findUserGroupForProject,
  isPastDeadline,
  memberProgress,
  resolveMemberUser,
  sortNodes,
  submissionsForNode,
} from "../utils/dashboard";
import StudentAiWorkspace from "../components/edu/StudentAiWorkspace";
import PeerReviewPanel from "../components/peer/PeerReviewPanel";
import {
  WorkspaceTabBar,
  type WorkspaceTab,
} from "../components/edu/WorkspaceTabs";

function leaderTabStorageKey(projectId: number) {
  return `leader-workspace-tab-${projectId}`;
}

function readLeaderWorkspaceTab(projectId: number): WorkspaceTab {
  if (Number.isNaN(projectId)) return "project";
  const saved = sessionStorage.getItem(leaderTabStorageKey(projectId));
  if (saved === "ai" || saved === "project" || saved === "peer-review") return saved;
  return "project";
}

interface MemberRow {
  userId: number;
  studentId: string;
  name: string;
  nodeLabels: string[];
  progress: number;
}

export default function LeaderDashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { projectId: projectIdParam } = useParams();
  const projectId = Number(projectIdParam);

  const [projectTitle, setProjectTitle] = useState("");
  const [projectDeadline, setProjectDeadline] = useState<string | undefined>();
  const [group, setGroup] = useState<Group | null>(null);
  const [nodes, setNodes] = useState<ProjectNode[]>([]);
  const [groupSubmissions, setGroupSubmissions] = useState<Submission[]>([]);
  const [mySubmissions, setMySubmissions] = useState<Submission[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [submittingNodeId, setSubmittingNodeId] = useState<number | null>(null);
  const [workspaceTab, setWorkspaceTab] = useState<WorkspaceTab>(() =>
    readLeaderWorkspaceTab(projectId)
  );

  useEffect(() => {
    if (!Number.isNaN(projectId)) {
      sessionStorage.setItem(leaderTabStorageKey(projectId), workspaceTab);
    }
  }, [workspaceTab, projectId]);

  useEffect(() => {
    if (!Number.isNaN(projectId)) {
      setWorkspaceTab(readLeaderWorkspaceTab(projectId));
    }
  }, [projectId]);

  const loadData = useCallback(async () => {
    if (!user) return;
    if (!projectIdParam || Number.isNaN(projectId)) {
      navigate("/leader", { replace: true });
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [{ data: groups }, { data: mine }, { data: project }] = await Promise.all([
        groupsApi.list(),
        submissionsApi.list(),
        projectsApi.get(projectId),
      ]);

      const myGroup = findUserGroupForProject(groups, user.id, projectId) ?? null;
      const sorted = sortNodes(project.nodes ?? []);

      setProjectTitle(project.title);
      setProjectDeadline(project.deadline);
      setGroup(myGroup);
      setNodes(sorted);
      setMySubmissions(mine);

      if (!myGroup) {
        setGroupSubmissions([]);
        setError("您尚未加入该项目的小组，请联系教师完成分组。仍可查看项目节点与个人提交。");
        return;
      }

      const { data: groupSubs } = await submissionsApi.groupSubmissions(myGroup.id);
      setGroupSubmissions(groupSubs);
      setError("");
    } catch {
      setError("加载数据失败，请刷新重试");
    } finally {
      setLoading(false);
    }
  }, [user, projectId, projectIdParam, navigate]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const nodeIds = useMemo(() => nodes.map((n) => n.id), [nodes]);

  const members: MemberRow[] = useMemo(() => {
    if (!group) return [];
    const memberIds = [...new Set(group.members.map((m) => m.user_id))];
    return memberIds.map((uid) => {
      const u = resolveMemberUser(uid, group.members, []);
      const subs = groupSubmissions.filter((s) => s.user_id === uid);
      const labels = subs.length
        ? subs.map((s) => {
            const nodeName =
              s.node?.name ?? nodes.find((n) => n.id === s.node_id)?.name ?? `节点#${s.node_id}`;
            const tag = s.file_path ? "（文件）" : "（文本）";
            return `${nodeName}${tag}`;
          })
        : ["暂无提交"];
      return {
        userId: uid,
        studentId: u?.student_id ?? String(uid),
        name: u?.name ?? "未知",
        nodeLabels: labels,
        progress: memberProgress(uid, nodeIds, groupSubmissions),
      };
    });
  }, [group, groupSubmissions, nodes, nodeIds]);

  const handleFileUpload = async (nodeId: number, file: File) => {
    const node = nodes.find((n) => n.id === nodeId);
    if (isPastDeadline(node?.deadline)) {
      alert("该节点已截止，无法上传");
      return;
    }
    setSubmittingNodeId(nodeId);
    try {
      const form = new FormData();
      form.append("node_id", String(nodeId));
      form.append("file", file);
      await submissionsApi.create(form);
      await loadData();
    } catch {
      alert("文件上传失败，请重试");
    } finally {
      setSubmittingNodeId(null);
    }
  };

  const pickFile = (nodeId: number) => {
    const input = document.createElement("input");
    input.type = "file";
    input.onchange = () => {
      const file = input.files?.[0];
      if (file) void handleFileUpload(nodeId, file);
    };
    input.click();
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white shadow-sm px-8 py-4 border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-6xl mx-auto flex justify-between items-center">
          <h1 className="text-xl font-bold text-blue-900 flex items-center gap-2">
            <i className="fa-solid fa-graduation-cap" />
            项目化学习系统
          </h1>
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={() => navigate("/leader")}
              className="text-sm text-blue-700 hover:text-blue-900 border border-blue-200 px-3 py-1.5 rounded-lg bg-blue-50"
            >
              <i className="fa-solid fa-arrow-left mr-1" />
              切换项目
            </button>
            <span className="bg-blue-50 text-blue-700 px-4 py-2 rounded-full text-sm font-semibold border border-blue-200">
              <i className="fa-solid fa-user-gear mr-2" />
              {user?.name} · 组长控制台
              {projectTitle ? ` · ${projectTitle}` : ""}
              {group ? ` · ${group.name}` : ""}
            </span>
            <button
              onClick={() => {
                logout();
                navigate("/login");
              }}
              className="text-sm text-slate-500 hover:text-red-500"
            >
              <i className="fa-solid fa-right-from-bracket mr-1" />
              退出
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        <WorkspaceTabBar
          active={workspaceTab}
          onChange={setWorkspaceTab}
          roleLabel="组长"
        />

        <div className={workspaceTab === "ai" ? "" : "hidden"}>
          <StudentAiWorkspace role="group_leader" projectId={projectId} projectDeadline={projectDeadline} />
        </div>

        <div className={workspaceTab === "peer-review" ? "" : "hidden"}>
          <PeerReviewPanel projectId={projectId} />
        </div>

        <div className={workspaceTab === "project" ? "space-y-8" : "hidden"}>
        <section className="bg-white rounded-xl p-6 shadow-sm border border-slate-200">
            <h2 className="text-lg font-bold text-blue-900 border-l-4 border-blue-900 pl-3 mb-5">
              <i className="fa-solid fa-users-gear mr-2" />
              组员分工与进度追踪
            </h2>

            {loading ? (
              <p className="text-slate-500 text-sm py-8 text-center">
                <i className="fa-solid fa-spinner fa-spin mr-2" />
                加载中...
              </p>
            ) : error && !group ? (
              <p className="text-amber-700 text-sm bg-amber-50 border border-amber-100 rounded-lg p-4">{error}</p>
            ) : !group ? (
              <p className="text-slate-500 text-sm">暂无小组数据，无法展示组员进度。</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-slate-500 border-b border-slate-200">
                      <th className="text-left py-3 pr-4">学号</th>
                      <th className="text-left py-3 pr-4">姓名</th>
                      <th className="text-left py-3 pr-4" style={{ width: "45%" }}>
                        已提交节点
                      </th>
                      <th className="text-left py-3">进度</th>
                    </tr>
                  </thead>
                  <tbody>
                    {members.map((m) => (
                      <tr key={m.userId} className="border-b border-slate-100">
                        <td className="py-4 pr-4 font-mono text-slate-500">{m.studentId}</td>
                        <td className="py-4 pr-4 font-medium">{m.name}</td>
                        <td className="py-4 pr-4">
                          <div className="space-y-1.5">
                            {m.nodeLabels.map((label, i) => (
                              <div
                                key={i}
                                className="bg-slate-100 px-3 py-2 rounded text-xs border-l-2 border-blue-400"
                              >
                                {label}
                              </div>
                            ))}
                          </div>
                        </td>
                        <td className="py-4">
                          <div className="flex items-center gap-2">
                            <div className="bg-slate-200 rounded-full h-2 w-20 overflow-hidden">
                              <div
                                className="bg-teal-500 h-full rounded-full transition-all"
                                style={{ width: `${m.progress}%` }}
                              />
                            </div>
                            <span className="text-xs font-bold text-slate-500">
                              {m.progress}%
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section>
            <h2 className="text-lg font-bold text-blue-900 border-l-4 border-blue-900 pl-3 mb-5">
              <i className="fa-solid fa-timeline mr-2" />
              组长个人成果提交区域
            </h2>

            {loading ? null : nodes.length === 0 ? (
              <p className="text-slate-400 text-sm">暂无项目节点。</p>
            ) : (
              <div className="relative pl-8">
                <div className="absolute left-3 top-2 bottom-0 w-0.5 bg-gradient-to-b from-blue-900 to-slate-300 rounded" />

                {nodes.map((node) => {
                  const nodeSubs = submissionsForNode(mySubmissions, node.id, user?.id);
                  const busy = submittingNodeId === node.id;
                  const nodeClosed = isPastDeadline(node.deadline);

                  return (
                    <div key={node.id} className="relative pb-8 pl-8 last:pb-0">
                      <div className="absolute left-[-4px] top-2 w-3.5 h-3.5 rounded-full bg-white border-4 border-blue-900" />

                      <div className="bg-white rounded-xl p-6 shadow-sm border border-slate-200">
                        <div className="flex items-center gap-3 mb-4">
                          <span className="bg-blue-900 text-white px-4 py-1 rounded text-sm font-bold">
                            {node.name}
                          </span>
                          <span className="text-sm text-slate-500 bg-slate-100 px-3 py-1 rounded flex items-center gap-1">
                            <i className="fa-regular fa-clock" />
                            截止：{formatDeadline(node.deadline)}
                          </span>
                        </div>

                        <div className="flex gap-4">
                          <div className="flex-1">
                            {nodeClosed ? (
                              <div className="w-full border-2 border-dashed border-red-200 rounded-lg p-8 text-center bg-red-50/50">
                                <i className="fa-solid fa-clock text-2xl text-red-400 mb-2" />
                                <p className="text-sm font-medium text-red-700">该节点已截止，无法上传</p>
                              </div>
                            ) : (
                            <button
                              onClick={() => !busy && pickFile(node.id)}
                              disabled={busy}
                              className="w-full border-2 border-dashed border-slate-300 rounded-lg p-8 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50 transition-colors disabled:opacity-60"
                            >
                              <i className="fa-solid fa-cloud-arrow-up text-2xl text-slate-400 mb-2" />
                              <p className="text-sm font-medium text-slate-600">
                                {busy ? "上传中..." : "点击上传文件"}
                              </p>
                              <p className="text-xs text-slate-400 mt-1">
                                支持 PDF, DOC, ZIP 等格式
                              </p>
                            </button>
                            )}
                          </div>
                          <div className="w-48">
                            <p className="text-xs font-semibold text-slate-500 mb-2">
                              已提交成果：
                            </p>
                            {nodeSubs.length > 0 ? (
                              <div className="space-y-1.5">
                                {nodeSubs.map((sub) => {
                                  const name =
                                    fileNameFromPath(sub.file_path) ||
                                    `[文本] ${(sub.text_content || "").slice(0, 16)}...`;
                                  return (
                                    <div
                                      key={sub.id}
                                      className="bg-slate-100 px-3 py-2 rounded text-xs flex items-center gap-2"
                                    >
                                      <i
                                        className={
                                          sub.file_path
                                            ? getFileIconClass(name)
                                            : "fa-solid fa-comment-alt text-purple-500"
                                        }
                                      />
                                      <span className="truncate flex-1">{name}</span>
                                      {sub.status === "evaluated" && (
                                        <button
                                          type="button"
                                          onClick={() => navigate(`/evaluation/${sub.id}`)}
                                          className="text-blue-600 hover:text-blue-800 shrink-0"
                                          title="查看评估"
                                        >
                                          <i className="fa-solid fa-chart-pie" />
                                        </button>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            ) : (
                              <p className="text-xs text-slate-400 italic text-center py-8 border border-dashed border-slate-200 rounded bg-slate-50">
                                暂无提交成果
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
