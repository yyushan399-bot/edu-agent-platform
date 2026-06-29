/** 教师端 —— 项目发布 + 分组管理 + 智能体异常介入 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../api/auth";
import {
  groupsApi,
  peerReviewApi,
  projectsApi,
  submissionsApi,
  usersApi,
  type Group,
  type Project,
  type Submission,
  type TeacherPeerReviewRecord,
  type User,
} from "../api/client";
import { fileNameFromPath, formatDeadline, sortNodes } from "../utils/dashboard";
import TeacherStudentChatPanel from "../components/TeacherStudentChatPanel";
import TeacherInterventionPanel from "../components/TeacherInterventionPanel";
import TeacherPeerReviewSidebar from "../components/teacher/TeacherPeerReviewSidebar";
import TeacherPeerReviewPanel from "../components/teacher/TeacherPeerReviewPanel";

export default function TeacherDashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [groupSubmissions, setGroupSubmissions] = useState<Submission[]>([]);
  const [peerReviews, setPeerReviews] = useState<TeacherPeerReviewRecord[]>([]);
  const [peerReviewsLoading, setPeerReviewsLoading] = useState(false);
  const [tab, setTab] = useState<"publish" | "groups" | "students" | "intervention" | "peer-review">("publish");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");

  const [projTitle, setProjTitle] = useState("");
  const [projDesc, setProjDesc] = useState("");
  const [projDeadline, setProjDeadline] = useState("");
  const [projGroupSize, setProjGroupSize] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [nodeName, setNodeName] = useState("");
  const [nodeDeadline, setNodeDeadline] = useState("");

  const [groupName, setGroupName] = useState("");
  const [groupProjectId, setGroupProjectId] = useState("");
  const [leaderStudentId, setLeaderStudentId] = useState("");
  const [memberStudentIds, setMemberStudentIds] = useState("");

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(""), 3000);
  };

  const loadPeerReviews = useCallback(async () => {
    setPeerReviewsLoading(true);
    try {
      const { data } = await peerReviewApi.listTeacher({ limit: 200 });
      setPeerReviews(data.items);
    } catch {
      setPeerReviews([]);
    } finally {
      setPeerReviewsLoading(false);
    }
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [projRes, groupRes, userRes] = await Promise.all([
        projectsApi.list(),
        groupsApi.list(),
        usersApi.list(),
      ]);
      setProjects(projRes.data);
      setGroups(groupRes.data);
      setUsers(userRes.data);

      const subs: Submission[] = [];
      for (const g of groupRes.data) {
        const { data } = await submissionsApi.groupSubmissions(g.id);
        subs.push(...data);
      }
      setGroupSubmissions(subs);
      await loadPeerReviews();
    } catch {
      showToast("加载数据失败");
    } finally {
      setLoading(false);
    }
  }, [loadPeerReviews]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (projects.length && selectedProjectId === null) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projects, selectedProjectId]);

  const selectedProject = useMemo(
    () => projects.find((p) => p.id === selectedProjectId) ?? null,
    [projects, selectedProjectId]
  );

  const linkedGroupProject = useMemo(
    () => projects.find((p) => String(p.id) === groupProjectId) ?? null,
    [projects, groupProjectId]
  );

  const studentUsers = useMemo(
    () =>
      users.filter((u) =>
        ["group_leader", "group_member"].includes(u.role)
      ),
    [users]
  );

  const fullWidthTab = tab === "students" || tab === "intervention" || tab === "peer-review";

  const sidebarPeerReviews = useMemo(() => {
    if (selectedProjectId == null) return peerReviews;
    return peerReviews.filter((r) => r.project_id === selectedProjectId);
  }, [peerReviews, selectedProjectId]);

  const handlePublish = async () => {
    if (!projTitle.trim()) {
      showToast("请输入项目名称");
      return;
    }
    if (!projDeadline.trim()) {
      showToast("请设置项目截止时间");
      return;
    }
    const groupSize = parseInt(projGroupSize, 10);
    if (!projGroupSize.trim() || Number.isNaN(groupSize) || groupSize < 1) {
      showToast("请设置有效的项目小组人数（至少 1 人）");
      return;
    }
    setBusy(true);
    try {
      const { data } = await projectsApi.create({
        title: projTitle.trim(),
        description: projDesc.trim() || undefined,
        deadline: new Date(projDeadline).toISOString(),
        group_size: groupSize,
      });
      setProjTitle("");
      setProjDesc("");
      setProjDeadline("");
      setProjGroupSize("");
      setSelectedProjectId(data.id);
      await loadAll();
      showToast("项目发布成功");
    } catch (err: unknown) {
      const ax = err as { response?: { status?: number; data?: { detail?: string } } };
      const detail = ax.response?.data?.detail;
      if (ax.response?.status === 403) {
        showToast(
          typeof detail === "string" && detail
            ? `${detail}，请确认以「授课教师」身份登录后重试`
            : "权限不足，请确认以「授课教师」身份登录后重试"
        );
      } else {
        showToast(typeof detail === "string" && detail ? detail : "项目发布失败");
      }
    } finally {
      setBusy(false);
    }
  };

  const handleAddNode = async () => {
    if (!selectedProjectId || !nodeName.trim()) {
      showToast("请选择项目并填写节点名称");
      return;
    }
    setBusy(true);
    try {
      const order = selectedProject?.nodes.length ?? 0;
      await projectsApi.createNode(selectedProjectId, {
        name: nodeName.trim(),
        deadline: nodeDeadline
          ? new Date(`${nodeDeadline}T00:00:00`).toISOString()
          : undefined,
        order,
      });
      setNodeName("");
      setNodeDeadline("");
      await loadAll();
      showToast("节点添加成功");
    } catch {
      showToast("节点添加失败");
    } finally {
      setBusy(false);
    }
  };

  const handleCreateGroup = async () => {
    if (!groupName.trim() || !leaderStudentId.trim()) {
      showToast("请填写组名和组长学号");
      return;
    }
    const leaderSid = leaderStudentId.trim();
    const members = memberStudentIds
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean);
    setBusy(true);
    try {
      await groupsApi.create({
        name: groupName.trim(),
        project_id: groupProjectId ? parseInt(groupProjectId, 10) : undefined,
        leader_student_id: leaderSid,
        member_student_ids: members,
      });
      setGroupName("");
      setLeaderStudentId("");
      setMemberStudentIds("");
      await loadAll();
      showToast("小组创建成功");
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } };
      showToast(ax.response?.data?.detail || "小组创建失败");
    } finally {
      setBusy(false);
    }
  };

  const resolveUserName = (userId: number) =>
    users.find((u) => u.id === userId)?.name ?? `用户#${userId}`;

  return (
    <div className="min-h-screen bg-slate-50">
      {toast && (
        <div className="fixed top-4 right-4 z-[100] bg-blue-900 text-white px-5 py-3 rounded-lg shadow-lg text-sm animate-fade-in">
          {toast}
        </div>
      )}

      <header className="bg-white shadow-sm px-8 py-4 border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto flex justify-between items-center">
          <h1 className="text-xl font-bold text-blue-900 flex items-center gap-2">
            <i className="fa-solid fa-chalkboard-user" />
            项目化学习系统 - 教师端
          </h1>
          <div className="flex items-center gap-4">
            <span className="bg-green-50 text-green-700 px-4 py-2 rounded-full text-sm font-semibold border border-green-200">
              <i className="fa-solid fa-user-shield mr-2" />
              {user?.name} · 授课教师
            </span>
            <button
              onClick={() => {
                logout();
                navigate("/login");
              }}
              className="text-sm text-slate-500 hover:text-red-500 transition-colors"
            >
              <i className="fa-solid fa-right-from-bracket mr-1" />
              退出
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-8 py-8 grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className={fullWidthTab ? "lg:col-span-3 space-y-8" : "lg:col-span-2 space-y-8"}>
          <div className="flex gap-1 bg-slate-200 rounded-lg p-1 w-fit flex-wrap">
            <button
              onClick={() => setTab("publish")}
              className={`px-5 py-2 rounded-md text-sm font-medium transition-colors ${
                tab === "publish"
                  ? "bg-white text-blue-900 shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              <i className="fa-solid fa-laptop-code mr-2" />
              项目发布
            </button>
            <button
              onClick={() => setTab("groups")}
              className={`px-5 py-2 rounded-md text-sm font-medium transition-colors ${
                tab === "groups"
                  ? "bg-white text-blue-900 shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              <i className="fa-solid fa-users-viewfinder mr-2" />
              分组管理
            </button>
            <button
              onClick={() => setTab("students")}
              className={`px-5 py-2 rounded-md text-sm font-medium transition-colors ${
                tab === "students"
                  ? "bg-white text-blue-900 shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              <i className="fa-solid fa-user-graduate mr-2" />
              学生管理
            </button>
            <button
              onClick={() => setTab("intervention")}
              className={`px-5 py-2 rounded-md text-sm font-medium transition-colors ${
                tab === "intervention"
                  ? "bg-white text-blue-900 shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              <i className="fa-solid fa-robot mr-2" />
              智能评分体 - 介入中心
            </button>
            <button
              onClick={() => setTab("peer-review")}
              className={`px-5 py-2 rounded-md text-sm font-medium transition-colors ${
                tab === "peer-review"
                  ? "bg-white text-blue-900 shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              <i className="fa-solid fa-users mr-2" />
              学生互评
              {peerReviews.length > 0 && (
                <span className="ml-1.5 bg-blue-100 text-blue-800 text-xs px-1.5 py-0.5 rounded-full">
                  {peerReviews.length}
                </span>
              )}
            </button>
          </div>

          {tab === "students" && (
            <TeacherStudentChatPanel students={studentUsers} />
          )}

          {tab === "intervention" && <TeacherInterventionPanel />}

          {tab === "peer-review" && (
            <TeacherPeerReviewPanel
              reviews={peerReviews}
              projects={projects}
              groups={groups}
              loading={peerReviewsLoading}
              selectedProjectId={selectedProjectId}
              onProjectChange={setSelectedProjectId}
            />
          )}

          {tab === "publish" && (
            <div className="space-y-6">
              <div className="bg-white rounded-xl p-8 shadow-sm border border-slate-200">
                <h2 className="text-lg font-bold text-blue-900 border-l-4 border-blue-900 pl-3 mb-6">
                  <i className="fa-solid fa-laptop-code mr-2" />
                  全新项目化学习任务发布
                </h2>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-semibold text-slate-500 mb-1">
                      项目名称
                    </label>
                    <input
                      type="text"
                      value={projTitle}
                      onChange={(e) => setProjTitle(e.target.value)}
                      placeholder="如：基于机器学习的空气质量预测系统设计"
                      className="w-full px-4 py-2.5 border border-slate-300 rounded-lg text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-slate-500 mb-1">
                      项目简述与核心指南
                    </label>
                    <textarea
                      value={projDesc}
                      onChange={(e) => setProjDesc(e.target.value)}
                      placeholder="请输入项目目标、最终成果交付规范..."
                      rows={3}
                      className="w-full px-4 py-2.5 border border-slate-300 rounded-lg text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 resize-none"
                    />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-semibold text-slate-500 mb-1">
                        项目截止时间
                      </label>
                      <input
                        type="datetime-local"
                        value={projDeadline}
                        onChange={(e) => setProjDeadline(e.target.value)}
                        className="w-full px-4 py-2.5 border border-slate-300 rounded-lg text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                      />
                      <p className="text-xs text-slate-400 mt-1">
                        组长可在截止 30 天后查看小组报告三维度得分与雷达图
                      </p>
                    </div>
                    <div>
                      <label className="block text-sm font-semibold text-slate-500 mb-1">
                        项目小组人数
                      </label>
                      <input
                        type="number"
                        min={1}
                        max={50}
                        value={projGroupSize}
                        onChange={(e) => setProjGroupSize(e.target.value)}
                        placeholder="如：3（含组长）"
                        className="w-full px-4 py-2.5 border border-slate-300 rounded-lg text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                      />
                      <p className="text-xs text-slate-400 mt-1">含组长在内的每组人数上限</p>
                    </div>
                  </div>
                  <button
                    onClick={() => void handlePublish()}
                    disabled={busy}
                    className="bg-blue-900 text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors flex items-center gap-2 disabled:opacity-60"
                  >
                    <i className="fa-solid fa-paper-plane" />
                    {busy ? "发布中..." : "发布至全班学生端"}
                  </button>
                </div>

                {projects.length > 0 && (
                  <div className="mt-6 pt-6 border-t border-slate-200">
                    <h3 className="text-sm font-semibold text-slate-500 mb-3">
                      已发布项目 ({projects.length})
                    </h3>
                    <div className="space-y-2">
                      {projects.map((p) => (
                        <button
                          key={p.id}
                          type="button"
                          onClick={() => setSelectedProjectId(p.id)}
                          className={`w-full flex items-center justify-between px-4 py-3 rounded-lg text-sm text-left transition-colors ${
                            selectedProjectId === p.id
                              ? "bg-blue-50 border border-blue-200"
                              : "bg-slate-50 hover:bg-slate-100"
                          }`}
                        >
                          <span className="font-medium text-slate-700">{p.title}</span>
                          <span className="text-slate-400 text-xs text-right shrink-0 ml-2">
                            {p.deadline ? `截止 ${formatDeadline(p.deadline)}` : "未设截止"}
                            {p.group_size ? ` · ${p.group_size} 人/组` : ""}
                            {` · ${p.nodes.length} 个节点`}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {selectedProject && (
                <div className="bg-white rounded-xl p-8 shadow-sm border border-slate-200">
                  <h2 className="text-lg font-bold text-blue-900 border-l-4 border-blue-900 pl-3 mb-6">
                    <i className="fa-solid fa-list-check mr-2" />
                    节点管理 · {selectedProject.title}
                  </h2>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                    <div className="md:col-span-2">
                      <label className="block text-xs font-semibold text-slate-500 mb-1">
                        节点名称
                      </label>
                      <input
                        type="text"
                        value={nodeName}
                        onChange={(e) => setNodeName(e.target.value)}
                        placeholder="如：节点一、文献调研"
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:border-blue-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-500 mb-1">
                        截止日期
                      </label>
                      <input
                        type="date"
                        value={nodeDeadline}
                        onChange={(e) => setNodeDeadline(e.target.value)}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:border-blue-500"
                      />
                    </div>
                  </div>
                  <button
                    onClick={() => void handleAddNode()}
                    disabled={busy}
                    className="bg-teal-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-teal-500 transition-colors disabled:opacity-60"
                  >
                    <i className="fa-solid fa-plus mr-1" />
                    添加节点
                  </button>

                  <div className="mt-6 space-y-2">
                    {sortNodes(selectedProject.nodes).map((node) => (
                      <div
                        key={node.id}
                        className="flex items-center justify-between bg-slate-50 px-4 py-3 rounded-lg text-sm"
                      >
                        <span className="font-medium">{node.name}</span>
                        <span className="text-slate-400 text-xs">
                          截止 {formatDeadline(node.deadline)}
                        </span>
                      </div>
                    ))}
                    {selectedProject.nodes.length === 0 && (
                      <p className="text-slate-400 text-sm text-center py-6">
                        暂无节点，请添加
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {tab === "groups" && (
            <div className="bg-white rounded-xl p-8 shadow-sm border border-slate-200">
              <h2 className="text-lg font-bold text-blue-900 border-l-4 border-blue-900 pl-3 mb-6">
                <i className="fa-solid fa-users-viewfinder mr-2" />
                学生项目分组配置
              </h2>

              <div className="bg-slate-50 p-5 rounded-lg border border-slate-200 space-y-4 mb-6">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-500 mb-1">
                      组别名称
                    </label>
                    <input
                      type="text"
                      value={groupName}
                      onChange={(e) => setGroupName(e.target.value)}
                      placeholder="第1组"
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:border-blue-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-500 mb-1">
                      关联项目
                    </label>
                    <select
                      value={groupProjectId}
                      onChange={(e) => setGroupProjectId(e.target.value)}
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:border-blue-500 bg-white"
                    >
                      <option value="">（可选）</option>
                      {projects.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.title}
                        </option>
                      ))}
                    </select>
                    {linkedGroupProject?.group_size ? (
                      <p className="text-xs text-slate-500 mt-1">
                        该项目要求 {linkedGroupProject.group_size} 人/组（含组长）
                      </p>
                    ) : null}
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-500 mb-1">
                      组长学号
                    </label>
                    <input
                      type="text"
                      value={leaderStudentId}
                      onChange={(e) => setLeaderStudentId(e.target.value)}
                      placeholder="2023101"
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:border-blue-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-500 mb-1">
                      组员学号（逗号分隔）
                    </label>
                    <input
                      type="text"
                      value={memberStudentIds}
                      onChange={(e) => setMemberStudentIds(e.target.value)}
                      placeholder="2023102, 2023103"
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:border-blue-500"
                    />
                  </div>
                </div>

                {studentUsers.length > 0 && (
                  <p className="text-xs text-slate-500">
                    学生参考：
                    {studentUsers.map((u) => `${u.name}（${u.student_id}）`).join(" · ")}
                  </p>
                )}

                <button
                  onClick={() => void handleCreateGroup()}
                  disabled={busy}
                  className="bg-teal-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-teal-500 transition-colors disabled:opacity-60"
                >
                  <i className="fa-solid fa-plus mr-1" />
                  创建小组
                </button>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-slate-500 border-b border-slate-200">
                      <th className="text-left py-3 px-2">组别</th>
                      <th className="text-left py-3 px-2">项目</th>
                      <th className="text-left py-3 px-2">组长</th>
                      <th className="text-left py-3 px-2">成员数</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groups.map((g) => (
                      <tr
                        key={g.id}
                        className="border-b border-slate-100 hover:bg-slate-50"
                      >
                        <td className="py-3 px-2 font-medium">{g.name}</td>
                        <td className="py-3 px-2 text-slate-500">
                          {projects.find((p) => p.id === g.project_id)?.title ?? "—"}
                        </td>
                        <td className="py-3 px-2 text-slate-500">
                          {resolveUserName(g.leader_id ?? 0)}
                        </td>
                        <td className="py-3 px-2">{g.members.length} 人</td>
                      </tr>
                    ))}
                    {groups.length === 0 && !loading && (
                      <tr>
                        <td colSpan={4} className="py-8 text-center text-slate-400">
                          暂无分组
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {tab !== "students" && tab !== "intervention" && tab !== "peer-review" && (
        <div className="space-y-4">
          <TeacherPeerReviewSidebar
            reviews={sidebarPeerReviews}
            loading={peerReviewsLoading}
            onViewAll={() => setTab("peer-review")}
          />

          <div className="bg-white rounded-xl p-6 shadow-sm border border-slate-200">
            <h3 className="text-sm font-bold text-slate-600 mb-4">
              <i className="fa-solid fa-inbox mr-2" />
              小组提交 ({groupSubmissions.length})
            </h3>
            {groupSubmissions.length === 0 ? (
              <p className="text-xs text-slate-400 text-center py-6">暂无提交</p>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto text-xs">
                {groupSubmissions.slice(0, 15).map((sub) => (
                  <div
                    key={sub.id}
                    className="flex justify-between items-start bg-slate-50 px-3 py-2 rounded"
                  >
                    <div className="min-w-0">
                      <p className="font-medium text-slate-700 truncate">
                        {resolveUserName(sub.user_id)}
                      </p>
                      <p className="text-slate-400 truncate">
                        {sub.node?.name} ·{" "}
                        {fileNameFromPath(sub.file_path) || "文本提交"}
                      </p>
                    </div>
                    <div className="flex items-center gap-1 shrink-0 ml-2">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          sub.status === "evaluated"
                            ? "bg-green-100 text-green-700"
                            : "bg-amber-100 text-amber-700"
                        }`}
                      >
                        {sub.status === "evaluated" ? "已评估" : "待评估"}
                      </span>
                      {sub.status === "evaluated" && (
                        <button
                          type="button"
                          onClick={() => navigate(`/evaluation/${sub.id}`)}
                          className="text-blue-600 hover:text-blue-800 p-1"
                          title="查看评估"
                        >
                          <i className="fa-solid fa-chart-pie" />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="bg-white rounded-xl p-6 shadow-sm border border-slate-200">
            <h3 className="text-sm font-bold text-slate-600 mb-4">
              <i className="fa-solid fa-list mr-2" />
              项目概览
            </h3>
            <div className="text-sm text-slate-500 space-y-3">
              <div className="flex justify-between">
                <span>项目总数</span>
                <span className="font-bold text-blue-900">{projects.length}</span>
              </div>
              <div className="flex justify-between">
                <span>小组总数</span>
                <span className="font-bold text-blue-900">{groups.length}</span>
              </div>
            </div>
          </div>
        </div>
        )}
      </main>
    </div>
  );
}
