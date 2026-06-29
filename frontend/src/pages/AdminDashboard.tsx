/** 管理员端 —— 四面板：用户 / 分组追踪 / 报告终审 / 评价中心 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../api/auth";
import AdminProjectPortal from "../components/AdminProjectPortal";
import { useToast } from "../components/Toast";
import {
  groupsApi,
  groupPblApi,
  projectsApi,
  submissionsApi,
  teacherInterventionApi,
  usersApi,
  type Group,
  type Project,
  type Submission,
  type TeacherInterventionRecord,
  type User,
} from "../api/client";
import {
  fileNameFromPath,
  formatDateTime,
  formatDeadline,
  memberProgress,
  resolveMemberUser,
  sortNodes,
} from "../utils/dashboard";

type AdminTab = "users" | "groups" | "reports" | "evaluations";

const PROJECT_SCOPED_TABS: AdminTab[] = ["groups", "reports", "evaluations"];

const TAB_META: Record<AdminTab, { title: string; icon: string; label: string }> = {
  users: {
    title: "用户凭证与账户中心",
    icon: "fa-users-rectangle",
    label: "用户凭证与账户中心",
  },
  groups: {
    title: "分组分工与节点追踪",
    icon: "fa-diagram-project",
    label: "分组分工与节点追踪",
  },
  reports: {
    title: "最终项目报告终审库",
    icon: "fa-file-shield",
    label: "最终项目报告终审库",
  },
  evaluations: {
    title: "形成性评价中心",
    icon: "fa-chart-pie",
    label: "形成性评价中心",
  },
};

const PAGE_SIZE = 10;

export default function AdminDashboard() {
  const { user, logout } = useAuth();
  const { showToast } = useToast();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [tab, setTab] = useState<AdminTab>("users");
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [users, setUsers] = useState<User[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [allSubmissions, setAllSubmissions] = useState<Submission[]>([]);
  const [groupPblRecords, setGroupPblRecords] = useState<TeacherInterventionRecord[]>([]);
  const [expandedPblId, setExpandedPblId] = useState<number | null>(null);
  const [downloadingPblId, setDownloadingPblId] = useState<number | null>(null);
  const [userPage, setUserPage] = useState(0);
  const [expandedGroupIds, setExpandedGroupIds] = useState<Set<number>>(new Set());

  const [newSid, setNewSid] = useState("");
  const [newName, setNewName] = useState("");
  const [newRole, setNewRole] = useState("group_member");

  const [importProjectId, setImportProjectId] = useState<number | "">("");
  const [replaceExistingGroups, setReplaceExistingGroups] = useState(true);
  const [importing, setImporting] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [userRes, groupRes, projRes, pblRes] = await Promise.all([
        usersApi.list(),
        groupsApi.list(),
        projectsApi.list(),
        teacherInterventionApi.listEvaluations(),
      ]);
      setUsers(userRes.data);
      setGroups(groupRes.data);
      setProjects(projRes.data);
      setGroupPblRecords(pblRes.data);

      const subs: Submission[] = [];
      for (const g of groupRes.data) {
        const { data } = await submissionsApi.groupSubmissions(g.id);
        subs.push(...data);
      }
      setAllSubmissions(subs);
    } catch {
      showToast("加载数据失败", "error");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    if (projects.length > 0 && importProjectId === "") {
      setImportProjectId(projects[0].id);
    }
  }, [projects, importProjectId]);

  const projectById = useMemo(
    () => new Map(projects.map((p) => [p.id, p])),
    [projects]
  );

  const groupCountByProject = useMemo(() => {
    const map = new Map<number, number>();
    for (const g of groups) {
      if (g.project_id != null) {
        map.set(g.project_id, (map.get(g.project_id) ?? 0) + 1);
      }
    }
    return map;
  }, [groups]);

  const selectedProject = selectedProjectId
    ? projectById.get(selectedProjectId)
    : undefined;

  const projectGroups = useMemo(() => {
    if (!selectedProjectId) return [];
    return groups.filter((g) => g.project_id === selectedProjectId);
  }, [groups, selectedProjectId]);

  const projectNodeIdSet = useMemo(() => {
    const ids = new Set<number>();
    for (const n of selectedProject?.nodes ?? []) {
      ids.add(n.id);
    }
    return ids;
  }, [selectedProject]);

  const projectMemberIds = useMemo(() => {
    const ids = new Set<number>();
    for (const g of projectGroups) {
      for (const m of g.members) {
        ids.add(m.user_id);
      }
    }
    return ids;
  }, [projectGroups]);

  const projectSubmissions = useMemo(() => {
    if (!selectedProjectId) return [];
    return allSubmissions.filter(
      (s) => projectMemberIds.has(s.user_id) && projectNodeIdSet.has(s.node_id)
    );
  }, [allSubmissions, projectMemberIds, projectNodeIdSet, selectedProjectId]);

  /** 本项目各组在「小组报告评价」中最新一次上传（按 group_id 去重） */
  const projectGroupPblReports = useMemo(() => {
    if (!selectedProjectId) return [];
    const inProject = groupPblRecords
      .filter((r) => r.project_id === selectedProjectId)
      .sort(
        (a, b) =>
          new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
      );
    const latestByGroup = new Map<number, TeacherInterventionRecord>();
    for (const row of inProject) {
      if (row.group_id != null && !latestByGroup.has(row.group_id)) {
        latestByGroup.set(row.group_id, row);
      }
    }
    return [...latestByGroup.values()].sort(
      (a, b) =>
        new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
    );
  }, [groupPblRecords, selectedProjectId]);

  const formativeSubmissions = useMemo(
    () => projectSubmissions,
    [projectSubmissions]
  );

  const evaluatedSubmissions = useMemo(
    () =>
      formativeSubmissions
        .filter((s) => s.status === "evaluated")
        .sort(
          (a, b) =>
            new Date(b.submitted_at).getTime() - new Date(a.submitted_at).getTime()
        ),
    [formativeSubmissions]
  );

  const pendingSubmissions = useMemo(
    () => formativeSubmissions.filter((s) => s.status !== "evaluated"),
    [formativeSubmissions]
  );

  const pagedUsers = useMemo(() => {
    const start = userPage * PAGE_SIZE;
    return users.slice(start, start + PAGE_SIZE);
  }, [users, userPage]);

  const totalUserPages = Math.max(1, Math.ceil(users.length / PAGE_SIZE));

  const resolveName = (id: number) =>
    users.find((u) => u.id === id)?.name ?? `用户#${id}`;

  const resolveStudentName = (studentId: string) =>
    users.find((u) => u.student_id === studentId)?.name ?? studentId;

  const pblAuditLabel = (item: TeacherInterventionRecord) => {
    if (item.teacher_reviewed) return "审核通过";
    if (!item.max_review_rounds_reached) return "审核通过";
    if ((item.failed_dimension_views?.length ?? 0) > 0) return "审核未通过";
    return item.audit_passed ? "审核通过" : "审核未通过";
  };

  const handleDownloadPblReport = async (record: TeacherInterventionRecord) => {
    setDownloadingPblId(record.id);
    try {
      await groupPblApi.downloadReportFile(record.id, record.filename || "小组报告");
    } catch {
      showToast("报告文档下载失败或文件未存档", "error");
    } finally {
      setDownloadingPblId(null);
    }
  };

  const switchTab = (key: AdminTab) => {
    setTab(key);
    if (PROJECT_SCOPED_TABS.includes(key)) {
      setSelectedProjectId(null);
      setExpandedGroupIds(new Set());
    }
  };

  const toggleGroupExpanded = (groupId: number) => {
    setExpandedGroupIds((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  };

  const handleAddUser = async () => {
    if (!newSid.trim() || !newName.trim()) {
      showToast("请填写学号和姓名", "error");
      return;
    }
    try {
      await usersApi.create({
        student_id: newSid.trim(),
        name: newName.trim(),
        password: "12345",
        role: newRole,
      });
      showToast(`用户 ${newName} 创建成功，初始密码 12345`, "success");
      setNewSid("");
      setNewName("");
      await loadData();
    } catch {
      showToast("创建失败，学号可能已存在", "error");
    }
  };

  const handleImportGroups = async (file: File) => {
    if (importProjectId === "") {
      showToast("请先选择关联项目", "error");
      return;
    }
    setImporting(true);
    try {
      const { data } = await groupsApi.importSpreadsheet(
        importProjectId,
        file,
        replaceExistingGroups
      );
      showToast(data.message, "success");
      await loadData();
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      showToast(typeof msg === "string" ? msg : "分组表格导入失败", "error");
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleResetPwd = async (id: number, name: string) => {
    if (!confirm(`确认重置 ${name} 的密码为 12345？`)) return;
    await usersApi.resetPassword(id, "12345");
    showToast("密码已重置", "success");
  };

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`确认删除用户 ${name}？此操作不可撤销。`)) return;
    await usersApi.delete(id);
    showToast("用户已删除", "success");
    await loadData();
  };

  const roleBadge = (role: string) => {
    const colors: Record<string, string> = {
      admin: "bg-purple-100 text-purple-700",
      teacher: "bg-blue-100 text-blue-700",
      group_leader: "bg-amber-100 text-amber-700",
      group_member: "bg-slate-100 text-slate-600",
    };
    return colors[role] || "bg-slate-100 text-slate-600";
  };

  const roleLabel: Record<string, string> = {
    admin: "管理员",
    teacher: "教师",
    group_leader: "项目组长",
    group_member: "小组成员",
  };

  const showProjectPortal =
    PROJECT_SCOPED_TABS.includes(tab) && selectedProjectId === null && !loading;

  const showProjectContent =
    PROJECT_SCOPED_TABS.includes(tab) && selectedProjectId !== null && !loading;

  return (
    <div className="min-h-screen flex">
      <aside className="w-64 bg-slate-900 text-white flex flex-col shrink-0">
        <div className="px-6 py-6 text-lg font-bold flex items-center gap-3 border-b border-slate-700">
          <i className="fa-solid fa-screwdriver-wrench text-blue-400" />
          <span>项目化学习系统 · 管理端</span>
        </div>
        <nav className="flex-1 px-3 py-6 space-y-1">
          {(Object.keys(TAB_META) as AdminTab[]).map((key) => (
            <button
              key={key}
              onClick={() => switchTab(key)}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm transition-colors ${
                tab === key
                  ? "bg-blue-500 text-white font-medium shadow-lg shadow-blue-500/25"
                  : "text-slate-300 hover:bg-slate-700"
              }`}
            >
              <i className={`fa-solid ${TAB_META[key].icon}`} />
              <span className="text-left leading-snug">{TAB_META[key].label}</span>
            </button>
          ))}
        </nav>
        <div className="px-6 py-4 text-xs text-slate-500 border-t border-slate-700 flex items-center gap-2">
          <i className="fa-solid fa-shield-halved" />
          <span>系统管理员：{user?.name}</span>
        </div>
      </aside>

      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="bg-white px-8 py-4 shadow-sm border-b border-slate-200 flex justify-between items-center gap-4">
          <div className="flex items-center gap-3 min-w-0">
            {showProjectContent && selectedProject && (
              <button
                type="button"
                onClick={() => {
                  setSelectedProjectId(null);
                  setExpandedGroupIds(new Set());
                }}
                className="text-sm text-slate-500 hover:text-blue-600 shrink-0"
              >
                <i className="fa-solid fa-arrow-left mr-1" />
                返回项目列表
              </button>
            )}
            <h1 className="text-lg font-bold text-slate-800 truncate">
              {showProjectContent && selectedProject
                ? `${TAB_META[tab].title} · ${selectedProject.title}`
                : TAB_META[tab].title}
            </h1>
          </div>
          <button
            onClick={() => {
              logout();
              navigate("/login");
            }}
            className="text-sm text-slate-500 hover:text-red-500 shrink-0"
          >
            <i className="fa-solid fa-right-from-bracket mr-1" />
            退出
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-8">
          {loading && (
            <p className="text-center text-slate-500 py-16">
              <i className="fa-solid fa-spinner fa-spin mr-2" />
              加载中...
            </p>
          )}

          {showProjectPortal && (
            <AdminProjectPortal
              projects={projects}
              groupCountByProject={groupCountByProject}
              onSelect={setSelectedProjectId}
              hint={
                tab === "groups"
                  ? "选择项目后可查看分组分工与各节点提交进度。"
                  : tab === "reports"
                    ? "选择项目后可查看该项目各组组长提交的最终小组报告。"
                    : "选择项目后可查看该项目下的形成性评价记录与待评估队列。"
              }
            />
          )}

          {!loading && tab === "users" && (
            <div className="space-y-6">
              <div className="bg-white rounded-xl p-6 shadow-sm border border-slate-200">
                <h2 className="text-base font-bold text-slate-800 mb-2 flex items-center gap-2">
                  <i className="fa-solid fa-table text-blue-600" />
                  上传项目分组表格
                </h2>
                <p className="text-sm text-slate-500 mb-4">
                  表格第一列为组号，第二列为组长姓名，从第三列起为组员姓名（每行一组）。上传后分组将关联所选项目，并在「分组分工与节点追踪」中展示。
                </p>
                <div className="bg-slate-50 p-4 rounded-lg border border-slate-200 flex flex-wrap items-end gap-4">
                  <label className="flex flex-col gap-1 text-xs text-slate-500">
                    关联项目
                    <select
                      value={importProjectId}
                      onChange={(e) =>
                        setImportProjectId(e.target.value ? Number(e.target.value) : "")
                      }
                      className="px-3 py-2 border border-slate-300 rounded text-sm outline-none min-w-[220px] bg-white"
                    >
                      {projects.length === 0 ? (
                        <option value="">暂无项目</option>
                      ) : (
                        projects.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.title}
                          </option>
                        ))
                      )}
                    </select>
                  </label>
                  <label className="flex items-center gap-2 text-sm text-slate-600 pb-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={replaceExistingGroups}
                      onChange={(e) => setReplaceExistingGroups(e.target.checked)}
                      className="rounded"
                    />
                    覆盖该项目已有分组
                  </label>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv,.xlsx,.xlsm,.txt"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) void handleImportGroups(file);
                    }}
                  />
                  <button
                    type="button"
                    disabled={importing || projects.length === 0}
                    onClick={() => fileInputRef.current?.click()}
                    className="bg-teal-600 text-white px-4 py-2 rounded text-sm font-medium hover:bg-teal-500 disabled:opacity-50"
                  >
                    {importing ? (
                      <>
                        <i className="fa-solid fa-spinner fa-spin mr-1" />
                        导入中...
                      </>
                    ) : (
                      <>
                        <i className="fa-solid fa-upload mr-1" />
                        选择并上传表格
                      </>
                    )}
                  </button>
                </div>
                <p className="text-xs text-slate-400 mt-3">
                  支持 CSV、XLSX；Excel 可直接上传，或使用 UTF-8 / GBK 编码的 CSV。
                </p>
              </div>

              <div className="bg-white rounded-xl p-6 shadow-sm border border-slate-200">
                <div className="flex justify-between items-center mb-6">
                  <h2 className="text-base font-bold text-slate-800 flex items-center gap-2">
                    <i className="fa-solid fa-id-card" />
                    全系统注册用户信息档案（{users.length} 人）
                  </h2>
                  <button
                    onClick={() => {
                      if (confirm("确认将所有用户密码重置为 12345？")) {
                        Promise.all(
                          users.map((u) =>
                            usersApi.resetPassword(u.id, "12345").catch(() => {})
                          )
                        ).then(() => showToast("密码已全部重置", "success"));
                      }
                    }}
                    className="text-xs text-red-500 hover:text-red-700 flex items-center gap-1"
                  >
                    <i className="fa-solid fa-key" />
                    全员重置密码
                  </button>
                </div>

                <div className="bg-slate-50 p-4 rounded-lg border border-slate-200 flex items-center gap-3 mb-6 flex-wrap">
                  <span className="text-xs font-semibold text-slate-500">快捷注册：</span>
                  <input
                    type="text"
                    value={newSid}
                    onChange={(e) => setNewSid(e.target.value)}
                    placeholder="学号"
                    className="px-3 py-1.5 border border-slate-300 rounded text-sm outline-none"
                  />
                  <input
                    type="text"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="姓名"
                    className="px-3 py-1.5 border border-slate-300 rounded text-sm outline-none"
                  />
                  <select
                    value={newRole}
                    onChange={(e) => setNewRole(e.target.value)}
                    className="px-3 py-1.5 border border-slate-300 rounded text-sm outline-none"
                  >
                    <option value="group_member">小组成员</option>
                    <option value="group_leader">项目组长</option>
                    <option value="teacher">教师</option>
                    <option value="admin">管理员</option>
                  </select>
                  <button
                    onClick={() => void handleAddUser()}
                    className="bg-blue-500 text-white px-4 py-1.5 rounded text-sm font-medium hover:bg-blue-600"
                  >
                    <i className="fa-solid fa-plus mr-1" />
                    添加
                  </button>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-slate-500 border-b border-slate-200">
                        <th className="text-left py-3 px-3">学号</th>
                        <th className="text-left py-3 px-3">姓名</th>
                        <th className="text-left py-3 px-3">角色</th>
                        <th className="text-left py-3 px-3">状态</th>
                        <th className="text-left py-3 px-3">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pagedUsers.map((u) => (
                        <tr key={u.id} className="border-b border-slate-100 hover:bg-slate-50">
                          <td className="py-3 px-3 font-mono">{u.student_id}</td>
                          <td className="py-3 px-3 font-medium">{u.name}</td>
                          <td className="py-3 px-3">
                            <span
                              className={`inline-block px-2.5 py-0.5 rounded text-xs font-medium ${roleBadge(u.role)}`}
                            >
                              {roleLabel[u.role] || u.role}
                            </span>
                          </td>
                          <td className="py-3 px-3">
                            <span
                              className={`inline-block px-2 py-0.5 rounded text-xs ${
                                u.is_active
                                  ? "bg-green-100 text-green-700"
                                  : "bg-red-100 text-red-700"
                              }`}
                            >
                              {u.is_active ? "正常" : "禁用"}
                            </span>
                          </td>
                          <td className="py-3 px-3 flex gap-2">
                            <button
                              onClick={() => void handleResetPwd(u.id, u.name)}
                              className="text-xs bg-slate-100 hover:bg-slate-200 px-2.5 py-1 rounded"
                            >
                              重置密码
                            </button>
                            <button
                              onClick={() => void handleDelete(u.id, u.name)}
                              className="text-xs bg-red-50 text-red-600 hover:bg-red-100 px-2.5 py-1 rounded"
                            >
                              注销
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {users.length > PAGE_SIZE && (
                  <div className="flex justify-center items-center gap-3 mt-4 text-sm">
                    <button
                      disabled={userPage === 0}
                      onClick={() => setUserPage((p) => p - 1)}
                      className="px-3 py-1 rounded border border-slate-300 disabled:opacity-40"
                    >
                      上一页
                    </button>
                    <span className="text-slate-500">
                      {userPage + 1} / {totalUserPages}
                    </span>
                    <button
                      disabled={userPage >= totalUserPages - 1}
                      onClick={() => setUserPage((p) => p + 1)}
                      className="px-3 py-1 rounded border border-slate-300 disabled:opacity-40"
                    >
                      下一页
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}

          {showProjectContent && tab === "groups" && (
            <div className="space-y-4">
              {projectGroups.length === 0 ? (
                <EmptyPanel message="该项目尚未导入分组，请在「用户凭证与账户中心」上传分组表格" />
              ) : (
                projectGroups.map((group) => {
                  const nodes = sortNodes(selectedProject?.nodes ?? []);
                  const nodeIds = nodes.map((n) => n.id);
                  const groupSubs = projectSubmissions.filter((s) =>
                    group.members.some((m) => m.user_id === s.user_id)
                  );
                  const memberIds = [...new Set(group.members.map((m) => m.user_id))];
                  const expanded = expandedGroupIds.has(group.id);
                  const leaderName = resolveName(group.leader_id ?? 0);

                  return (
                    <section
                      key={group.id}
                      className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden"
                    >
                      <button
                        type="button"
                        onClick={() => toggleGroupExpanded(group.id)}
                        className="w-full flex flex-wrap items-center justify-between gap-3 px-6 py-4 text-left hover:bg-slate-50 transition-colors"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <i
                            className={`fa-solid fa-chevron-${expanded ? "down" : "right"} text-slate-400 text-xs shrink-0`}
                          />
                          <h2 className="text-base font-bold text-slate-800">
                            {group.name}
                            <span className="ml-2 text-sm font-normal text-slate-500">
                              组长：{leaderName}
                            </span>
                          </h2>
                        </div>
                        <span className="text-xs text-slate-400 shrink-0">
                          {memberIds.length} 名成员 · {nodes.length} 个节点
                        </span>
                      </button>

                      {expanded && (
                        <div className="px-6 pb-6 border-t border-slate-100">
                          {nodes.length > 0 && (
                            <div className="flex flex-wrap gap-2 my-4">
                              {nodes.map((node) => (
                                <span
                                  key={node.id}
                                  className="text-xs bg-blue-50 text-blue-800 px-3 py-1 rounded-full border border-blue-100"
                                >
                                  {node.name} · 截止 {formatDeadline(node.deadline)}
                                </span>
                              ))}
                            </div>
                          )}

                          <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="text-slate-500 border-b border-slate-200">
                                  <th className="text-left py-2 px-2">成员</th>
                                  <th className="text-left py-2 px-2">学号</th>
                                  <th className="text-left py-2 px-2">角色</th>
                                  <th className="text-left py-2 px-2">已提交节点</th>
                                  <th className="text-left py-2 px-2">进度</th>
                                </tr>
                              </thead>
                              <tbody>
                                {memberIds.map((uid) => {
                                  const u = resolveMemberUser(uid, group.members, users);
                                  const subs = groupSubs.filter((s) => s.user_id === uid);
                                  const labels =
                                    subs.length > 0
                                      ? subs.map(
                                          (s) =>
                                            s.node?.name ??
                                            nodes.find((n) => n.id === s.node_id)?.name ??
                                            `#${s.node_id}`
                                        )
                                      : ["暂无提交"];
                                  const progress = memberProgress(uid, nodeIds, groupSubs);
                                  const isLeader = uid === group.leader_id;
                                  return (
                                    <tr key={uid} className="border-b border-slate-100">
                                      <td className="py-3 px-2 font-medium">
                                        {u?.name ?? resolveName(uid)}
                                      </td>
                                      <td className="py-3 px-2 font-mono text-slate-500">
                                        {u?.student_id ?? "—"}
                                      </td>
                                      <td className="py-3 px-2">
                                        <span
                                          className={`text-xs px-2 py-0.5 rounded ${
                                            isLeader
                                              ? "bg-amber-100 text-amber-800"
                                              : "bg-slate-100 text-slate-600"
                                          }`}
                                        >
                                          {isLeader ? "组长" : "组员"}
                                        </span>
                                      </td>
                                      <td className="py-3 px-2">
                                        <div className="flex flex-wrap gap-1">
                                          {labels.map((l, i) => (
                                            <span
                                              key={i}
                                              className="text-xs bg-slate-100 px-2 py-0.5 rounded"
                                            >
                                              {l}
                                            </span>
                                          ))}
                                        </div>
                                      </td>
                                      <td className="py-3 px-2">
                                        <div className="flex items-center gap-2">
                                          <div className="w-16 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                                            <div
                                              className="h-full bg-teal-500 rounded-full"
                                              style={{ width: `${progress}%` }}
                                            />
                                          </div>
                                          <span className="text-xs text-slate-500">
                                            {progress}%
                                          </span>
                                        </div>
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}
                    </section>
                  );
                })
              )}
            </div>
          )}

          {showProjectContent && tab === "reports" && (
            <div className="bg-white rounded-xl p-6 shadow-sm border border-slate-200">
              <h2 className="text-base font-bold text-slate-800 mb-4 flex items-center gap-2">
                <i className="fa-solid fa-file-shield text-blue-600" />
                已收小组报告（{projectGroupPblReports.length}）
              </h2>
              <p className="text-sm text-slate-500 mb-4">
                展示本项目各组组长在「小组报告评价」中上传并已评价的报告文档（按小组取最新一次）。
              </p>
              {projectGroupPblReports.length === 0 ? (
                <EmptyPanel message="暂无组长在小组报告评价中提交的报告" />
              ) : (
                <div className="space-y-3">
                  {projectGroupPblReports.map((record) => {
                    const auditOk = pblAuditLabel(record) === "审核通过";
                    const expanded = expandedPblId === record.id;
                    const primary = record.primary_indicator_summary || [];
                    return (
                      <div
                        key={record.id}
                        className="border border-slate-200 rounded-lg overflow-hidden hover:bg-slate-50/50"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-3 p-4">
                          <div className="min-w-0">
                            <p className="font-medium text-slate-800">
                              {record.group_name ?? "未知小组"} · 组长{" "}
                              {resolveStudentName(record.student_id)}
                            </p>
                            <p className="text-sm text-slate-500 mt-1">
                              {record.filename || "（无文件名）"} ·{" "}
                              {formatDateTime(record.created_at)}
                            </p>
                            {record.final_score != null && (
                              <p className="text-xs text-slate-400 mt-1">
                                综合分 {Number(record.final_score).toFixed(2)}
                              </p>
                            )}
                          </div>
                          <div className="flex items-center gap-2 flex-wrap justify-end">
                            {(record.has_document || record.file_path) && (
                              <button
                                type="button"
                                disabled={downloadingPblId === record.id}
                                onClick={() => void handleDownloadPblReport(record)}
                                className="text-xs border border-slate-300 text-slate-700 px-3 py-1.5 rounded hover:bg-white disabled:opacity-50"
                              >
                                {downloadingPblId === record.id ? (
                                  <>
                                    <i className="fa-solid fa-spinner fa-spin mr-1" />
                                    下载中…
                                  </>
                                ) : (
                                  <>
                                    <i className="fa-solid fa-file-arrow-down mr-1" />
                                    下载报告
                                  </>
                                )}
                              </button>
                            )}
                            <span
                              className={`text-xs px-2 py-1 rounded font-medium ${
                                auditOk
                                  ? "bg-green-100 text-green-700"
                                  : "bg-amber-100 text-amber-700"
                              }`}
                            >
                              {pblAuditLabel(record)}
                            </span>
                            <button
                              type="button"
                              onClick={() =>
                                setExpandedPblId(expanded ? null : record.id)
                              }
                              className="text-xs bg-blue-600 text-white px-3 py-1.5 rounded hover:bg-blue-500"
                            >
                              {expanded ? "收起" : "查看评价"}
                            </button>
                          </div>
                        </div>
                        {expanded && (
                          <div className="border-t border-slate-100 bg-slate-50 px-4 py-3 text-sm space-y-3">
                            {!record.has_document && !record.file_path && (
                              <div className="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
                                该记录未存档原始文档（历史评价）。请组长重新提交后可下载 PDF/Word 原件。
                              </div>
                            )}
                            {record.report_text_preview && (
                              <div className="bg-white border border-slate-200 rounded-lg p-3">
                                <p className="text-xs font-semibold text-slate-500 mb-2">
                                  报告文本摘要
                                </p>
                                <p className="text-xs text-slate-600 whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
                                  {record.report_text_preview}
                                </p>
                              </div>
                            )}
                            {primary.length > 0 && (
                              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                                {primary.map((card, i) => (
                                  <div
                                    key={i}
                                    className="bg-white border border-slate-200 rounded-lg p-3"
                                  >
                                    <p className="text-xs text-slate-500">
                                      {String(card.primary_indicator ?? card.title ?? "指标")}
                                    </p>
                                    <p className="text-lg font-bold text-blue-900 mt-1">
                                      {card.mean != null
                                        ? Number(card.mean).toFixed(2)
                                        : "—"}
                                    </p>
                                  </div>
                                ))}
                              </div>
                            )}
                            {record.final_comment && (
                              <p className="text-slate-600 text-xs leading-relaxed">
                                {record.final_comment}
                              </p>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {showProjectContent && tab === "evaluations" && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <StatCard
                  label="已评估提交"
                  value={evaluatedSubmissions.length}
                  color="text-green-600"
                />
                <StatCard
                  label="待评估提交"
                  value={pendingSubmissions.length}
                  color="text-amber-600"
                />
                <StatCard
                  label="本项目小组数"
                  value={projectGroups.length}
                  color="text-blue-600"
                />
              </div>

              <div className="bg-white rounded-xl p-6 shadow-sm border border-slate-200">
                <h2 className="text-base font-bold text-slate-800 mb-4">
                  形成性评价记录
                </h2>
                {evaluatedSubmissions.length === 0 ? (
                  <EmptyPanel message="暂无已完成评估的节点提交" />
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-slate-500 border-b border-slate-200">
                          <th className="text-left py-3 px-2">学生</th>
                          <th className="text-left py-3 px-2">节点</th>
                          <th className="text-left py-3 px-2">提交时间</th>
                          <th className="text-left py-3 px-2">操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {evaluatedSubmissions.map((sub) => (
                          <tr key={sub.id} className="border-b border-slate-100 hover:bg-slate-50">
                            <td className="py-3 px-2 font-medium">
                              {resolveName(sub.user_id)}
                            </td>
                            <td className="py-3 px-2 text-slate-600">
                              {sub.node?.name ?? `节点#${sub.node_id}`}
                            </td>
                            <td className="py-3 px-2 text-slate-500">
                              {new Date(sub.submitted_at).toLocaleString("zh-CN")}
                            </td>
                            <td className="py-3 px-2">
                              <button
                                onClick={() => navigate(`/evaluation/${sub.id}`)}
                                className="text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-500"
                              >
                                查看评估报告
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {pendingSubmissions.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-6">
                  <h3 className="text-sm font-bold text-amber-800 mb-3">
                    待评估队列（{pendingSubmissions.length}）
                  </h3>
                  <div className="space-y-2 max-h-48 overflow-y-auto">
                    {pendingSubmissions.slice(0, 8).map((sub) => (
                      <p key={sub.id} className="text-xs text-amber-900">
                        {resolveName(sub.user_id)} · {sub.node?.name ?? "节点"} ·{" "}
                        {fileNameFromPath(sub.file_path) || "文本提交"}
                      </p>
                    ))}
                  </div>
                  <p className="text-xs text-amber-700 mt-3">
                    请由授课教师在教师端触发智能体评估
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function EmptyPanel({ message }: { message: string }) {
  return (
    <div className="text-center py-16 text-slate-400">
      <i className="fa-solid fa-inbox text-4xl mb-3" />
      <p className="text-sm">{message}</p>
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className={`text-3xl font-bold ${color}`}>{value}</p>
    </div>
  );
}
