/** 组员端 —— 时间轴节点提交成果 */
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../api/auth";
import {
  groupsApi,
  projectsApi,
  submissionsApi,
  type ProjectNode,
  type Submission,
} from "../api/client";
import {
  fileNameFromPath,
  findUserGroupForProject,
  formatDeadline,
  getFileIconClass,
  isPastDeadline,
  sortNodes,
  submissionsForNode,
} from "../utils/dashboard";
import StudentAiWorkspace from "../components/edu/StudentAiWorkspace";
import PeerReviewPanel from "../components/peer/PeerReviewPanel";
import {
  WorkspaceBody,
  WorkspaceTabBar,
  type WorkspaceTab,
} from "../components/edu/WorkspaceTabs";

export default function MemberDashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { projectId: projectIdParam } = useParams();
  const projectId = Number(projectIdParam);

  const [projectTitle, setProjectTitle] = useState("");
  const [projectDeadline, setProjectDeadline] = useState<string | undefined>();
  const [groupName, setGroupName] = useState("");
  const [workspaceTab, setWorkspaceTab] = useState<WorkspaceTab>("project");
  const [nodes, setNodes] = useState<ProjectNode[]>([]);
  const [mySubmissions, setMySubmissions] = useState<Submission[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const [submittingNodeId, setSubmittingNodeId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<Record<number, "file" | "text">>({});
  const [textInputs, setTextInputs] = useState<Record<number, string>>({});

  const loadData = useCallback(async () => {
    if (!user) return;
    if (!projectIdParam || Number.isNaN(projectId)) {
      navigate("/member", { replace: true });
      return;
    }
    setLoading(true);
    setError("");
    setWarning("");
    try {
      const [{ data: groups }, { data: submissions }, { data: project }] = await Promise.all([
        groupsApi.list(),
        submissionsApi.list(),
        projectsApi.get(projectId),
      ]);
      const myGroup = findUserGroupForProject(groups, user.id, projectId);
      const sorted = sortNodes(project.nodes ?? []);
      setProjectTitle(project.title);
      setProjectDeadline(project.deadline);
      setGroupName(myGroup?.name ?? "");
      setNodes(sorted);
      setMySubmissions(submissions);
      setActiveTab((prev) => {
        const next = { ...prev };
        for (const node of sorted) {
          if (!next[node.id]) next[node.id] = "file";
        }
        return next;
      });
      if (!myGroup) {
        setWarning("您尚未加入该项目的小组，仍可查看项目节点并提交个人成果。");
      }
    } catch {
      setError("加载项目数据失败，请刷新重试");
    } finally {
      setLoading(false);
    }
  }, [user, projectId, projectIdParam, navigate]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleFileUpload = async (nodeId: number, files: FileList | null) => {
    if (!files?.length) return;
    const node = nodes.find((n) => n.id === nodeId);
    if (isPastDeadline(node?.deadline)) {
      alert("该节点已截止，无法上传");
      return;
    }
    setSubmittingNodeId(nodeId);
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("node_id", String(nodeId));
        form.append("file", file);
        await submissionsApi.create(form);
      }
      const { data } = await submissionsApi.list();
      setMySubmissions(data);
    } catch {
      alert("文件上传失败，请重试");
    } finally {
      setSubmittingNodeId(null);
    }
  };

  const handleTextSubmit = async (nodeId: number) => {
    const node = nodes.find((n) => n.id === nodeId);
    if (isPastDeadline(node?.deadline)) {
      alert("该节点已截止，无法提交");
      return;
    }
    const text = textInputs[nodeId]?.trim();
    if (!text) {
      alert("请输入文字后再提交");
      return;
    }
    setSubmittingNodeId(nodeId);
    try {
      const form = new FormData();
      form.append("node_id", String(nodeId));
      form.append("text_content", text);
      await submissionsApi.create(form);
      setTextInputs((prev) => ({ ...prev, [nodeId]: "" }));
      const { data } = await submissionsApi.list();
      setMySubmissions(data);
    } catch {
      alert("文本提交失败，请重试");
    } finally {
      setSubmittingNodeId(null);
    }
  };

  const handleDelete = async (submissionId: number) => {
    if (!confirm("确定删除这条提交吗？")) return;
    try {
      await submissionsApi.delete(submissionId);
      setMySubmissions((prev) => prev.filter((s) => s.id !== submissionId));
    } catch {
      alert("删除失败，请重试");
    }
  };

  const pickFiles = (nodeId: number) => {
    const input = document.createElement("input");
    input.type = "file";
    input.multiple = true;
    input.onchange = () => void handleFileUpload(nodeId, input.files);
    input.click();
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white shadow-sm px-8 py-4 border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-4xl mx-auto flex justify-between items-center">
          <h1 className="text-xl font-bold text-blue-900 flex items-center gap-2">
            <i className="fa-solid fa-graduation-cap" />
            项目化学习系统
          </h1>
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={() => navigate("/member")}
              className="text-sm text-blue-700 hover:text-blue-900 border border-blue-200 px-3 py-1.5 rounded-lg bg-blue-50"
            >
              <i className="fa-solid fa-arrow-left mr-1" />
              切换项目
            </button>
            <span className="bg-slate-100 text-slate-700 px-4 py-2 rounded-full text-sm font-medium border border-slate-200">
              <i className="fa-solid fa-user mr-2" />
              {user?.name} · 组员控制台
              {projectTitle ? ` · ${projectTitle}` : ""}
              {groupName ? ` · ${groupName}` : ""}
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

      <div className="max-w-4xl mx-auto px-6 py-10">
        <WorkspaceTabBar
          active={workspaceTab}
          onChange={setWorkspaceTab}
          roleLabel="组员"
        />

        <WorkspaceBody
          active={workspaceTab}
          aiContent={<StudentAiWorkspace role="group_member" projectId={projectId} projectDeadline={projectDeadline} />}
          peerReviewContent={<PeerReviewPanel projectId={projectId} />}
          projectContent={
            <>
        {loading && (
          <p className="text-center text-slate-500 py-16">
            <i className="fa-solid fa-spinner fa-spin mr-2" />
            加载中...
          </p>
        )}

        {!loading && warning && (
          <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-lg p-4 mb-6 text-sm">
            {warning}
          </div>
        )}

        {!loading && error && (
          <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-lg p-4 mb-6 text-sm">
            {error}
            <button
              onClick={() => void loadData()}
              className="ml-3 underline hover:no-underline"
            >
              重试
            </button>
          </div>
        )}

        {!loading && !error && nodes.length === 0 && (
          <p className="text-center text-slate-400 py-16">
            暂无项目节点，请联系教师发布项目并配置节点。
          </p>
        )}

        {!loading && nodes.length > 0 && (
          <div className="relative pl-10">
            <div className="absolute left-4 top-2 bottom-0 w-0.5 bg-gradient-to-b from-blue-900 to-slate-300 rounded" />

            {nodes.map((node) => {
              const nodeSubs = submissionsForNode(mySubmissions, node.id);
              const busy = submittingNodeId === node.id;
              const nodeClosed = isPastDeadline(node.deadline);

              return (
                <div key={node.id} className="relative pb-12 last:pb-0">
                  <div className="absolute left-[-4px] top-2.5 w-3.5 h-3.5 rounded-full bg-white border-4 border-blue-900" />

                  <div className="bg-white rounded-xl p-6 shadow-sm border border-slate-200">
                    <div className="flex items-center gap-3 mb-5">
                      <span className="bg-blue-900 text-white px-4 py-1 rounded text-sm font-bold tracking-wide">
                        {node.name}
                      </span>
                      <span className="text-sm text-slate-500 bg-slate-100 px-3 py-1 rounded flex items-center gap-1">
                        <i className="fa-regular fa-clock" />
                        截止日期：{formatDeadline(node.deadline)}
                      </span>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                      <div className="border border-slate-200 rounded-lg overflow-hidden bg-slate-50">
                        <div className="flex border-b border-slate-200">
                          <button
                            onClick={() =>
                              setActiveTab((p) => ({ ...p, [node.id]: "file" }))
                            }
                            className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
                              (activeTab[node.id] ?? "file") === "file"
                                ? "bg-white text-blue-900 font-bold"
                                : "text-slate-400 hover:text-slate-600"
                            }`}
                          >
                            <i className="fa-solid fa-file-arrow-up mr-1" />
                            文件上传
                          </button>
                          <button
                            onClick={() =>
                              setActiveTab((p) => ({ ...p, [node.id]: "text" }))
                            }
                            className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
                              activeTab[node.id] === "text"
                                ? "bg-white text-blue-900 font-bold"
                                : "text-slate-400 hover:text-slate-600"
                            }`}
                          >
                            <i className="fa-solid fa-pen-to-square mr-1" />
                            文本提交
                          </button>
                        </div>

                        <div className="p-3">
                          {nodeClosed ? (
                            <div className="border-2 border-dashed border-red-200 rounded-lg p-6 text-center bg-red-50/50">
                              <i className="fa-solid fa-clock text-xl text-red-400 mb-2" />
                              <p className="text-xs text-red-700 font-medium">该节点已截止，无法提交</p>
                            </div>
                          ) : (activeTab[node.id] ?? "file") === "file" ? (
                            <div
                              onClick={() => !busy && pickFiles(node.id)}
                              className={`border-2 border-dashed border-slate-300 rounded-lg p-6 text-center transition-all ${
                                busy
                                  ? "opacity-60 cursor-wait"
                                  : "cursor-pointer hover:border-blue-400 hover:bg-white"
                              }`}
                            >
                              <i className="fa-solid fa-cloud-arrow-up text-xl text-slate-400 mb-2" />
                              <p className="text-xs text-slate-500">
                                {busy ? "上传中..." : "点击选择文件上传"}
                              </p>
                            </div>
                          ) : (
                            <div className="space-y-2">
                              <textarea
                                value={textInputs[node.id] || ""}
                                onChange={(e) =>
                                  setTextInputs((p) => ({
                                    ...p,
                                    [node.id]: e.target.value,
                                  }))
                                }
                                placeholder="请在此处直接输入或粘贴文本内容..."
                                rows={4}
                                className="w-full p-2.5 border border-slate-300 rounded text-sm outline-none focus:border-blue-500 resize-none"
                              />
                              <button
                                onClick={() => void handleTextSubmit(node.id)}
                                disabled={busy}
                                className="w-full bg-blue-900 text-white py-1.5 rounded text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-60"
                              >
                                {busy ? "提交中..." : "提交文本"}
                              </button>
                            </div>
                          )}
                        </div>
                      </div>

                      <div>
                        <p className="text-xs font-semibold text-slate-500 mb-2">
                          已提交成果：
                        </p>
                        {nodeSubs.length === 0 ? (
                          <p className="text-xs text-slate-400 italic text-center py-10 border border-dashed border-slate-200 rounded bg-slate-50">
                            暂无提交成果
                          </p>
                        ) : (
                          <div className="space-y-1.5">
                            {nodeSubs.map((sub) => {
                              const fileName = fileNameFromPath(sub.file_path);
                              return (
                                <div
                                  key={sub.id}
                                  className="bg-slate-100 px-3 py-2 rounded text-xs flex items-center justify-between gap-2"
                                >
                                  <div className="flex items-center gap-2 overflow-hidden min-w-0">
                                    {fileName ? (
                                      <>
                                        <i className={getFileIconClass(fileName)} />
                                        <span className="truncate">{fileName}</span>
                                      </>
                                    ) : (
                                      <>
                                        <i className="fa-solid fa-comment-alt text-purple-500" />
                                        <span className="truncate">
                                          [文本] &quot;{(sub.text_content || "").slice(0, 30)}
                                          {(sub.text_content?.length ?? 0) > 30 ? "..." : ""}&quot;
                                        </span>
                                      </>
                                    )}
                                  </div>
                                  <button
                                    onClick={() => void handleDelete(sub.id)}
                                    className="text-red-400 hover:text-red-600 shrink-0"
                                    title="删除"
                                  >
                                    <i className="fa-solid fa-trash-can" />
                                  </button>
                                  {sub.status === "evaluated" && (
                                    <button
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
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
            </>
          }
        />
      </div>
    </div>
  );
}
