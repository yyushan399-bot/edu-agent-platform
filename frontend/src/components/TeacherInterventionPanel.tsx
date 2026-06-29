/** 教师端：智能评分体介入中心 — 按项目分组的小组报告十二维度管理 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  groupPblApi,
  projectsApi,
  teacherInterventionApi,
  type GroupPblDimension,
  type Project,
  type TeacherInterventionRecord,
} from "../api/client";
import { formatDateTime } from "../utils/dashboard";

function formatScore(value: unknown): string {
  if (value == null || value === "") return "—";
  const num = Number(value);
  return Number.isNaN(num) ? String(value) : num.toFixed(2);
}

function initEditsFromDims(dims: GroupPblDimension[]): Record<string, string> {
  const next: Record<string, string> = {};
  for (const dim of dims) {
    const name = String(dim.dimension_name || "");
    if (name) next[name] = String(dim.mean ?? "");
  }
  return next;
}

function isTeacherAuditPassed(item: TeacherInterventionRecord): boolean {
  if (item.teacher_reviewed) return true;
  if (!item.max_review_rounds_reached) return true;
  if ((item.failed_dimension_views?.length ?? 0) > 0) return false;
  return item.audit_passed;
}

function auditStatusLabel(item: TeacherInterventionRecord): string {
  return isTeacherAuditPassed(item) ? "审核通过" : "审核未通过";
}

type ProjectSection = {
  key: string;
  projectId: number | null;
  title: string;
  deadline?: string;
  items: TeacherInterventionRecord[];
};

interface EvaluationCardProps {
  item: TeacherInterventionRecord;
  isOpen: boolean;
  busyId: number | null;
  downloadingId: number | null;
  editScores: Record<number, Record<string, string>>;
  onToggle: () => void;
  onApprove: (id: number) => void;
  onInitEdit: (record: TeacherInterventionRecord) => void;
  onSaveScores: (record: TeacherInterventionRecord, dims: GroupPblDimension[]) => void;
  onEditChange: (recordId: number, dimName: string, value: string) => void;
  onDownloadReport: (record: TeacherInterventionRecord) => void;
}

function EvaluationRecordCard({
  item,
  isOpen,
  busyId,
  downloadingId,
  editScores,
  onToggle,
  onApprove,
  onInitEdit,
  onSaveScores,
  onEditChange,
  onDownloadReport,
}: EvaluationCardProps) {
  const pendingReview = item.needs_teacher_intervention && !item.teacher_reviewed;
  const hasEdits = Boolean(editScores[item.id]);
  const failedNames = new Set(
    (item.failed_dimension_views || []).map((d) => String(d.dimension_name || ""))
  );
  const needsHighlight =
    item.needs_teacher_intervention && !item.teacher_reviewed && failedNames.size > 0;
  const editable = Boolean(editScores[item.id]);

  return (
    <div
      className={`border rounded-xl overflow-hidden ${
        pendingReview ? "border-red-200" : "border-amber-100"
      }`}
    >
      <button
        type="button"
        onClick={onToggle}
        className={`w-full flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-left transition-colors ${
          pendingReview
            ? "bg-red-50/60 hover:bg-red-50"
            : "bg-amber-50/40 hover:bg-amber-50/70"
        }`}
      >
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-slate-800 text-sm">
            {item.group_name || "未关联小组"} · {item.student_id}
          </p>
          <p className="text-xs text-slate-500 mt-0.5 truncate">
            {item.filename || "（无文件名）"} · 综合 {formatScore(item.final_score)} · 12维均分{" "}
            {formatScore(item.dimension_mean_score)}
            {item.teacher_modified ? " · 教师已改分" : ""}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {(item.has_document || item.file_path) && (
            <button
              type="button"
              disabled={downloadingId === item.id}
              onClick={(e) => {
                e.stopPropagation();
                onDownloadReport(item);
              }}
              className="text-[10px] border border-slate-300 text-slate-700 px-2 py-1 rounded hover:bg-white disabled:opacity-50"
              title="下载组长在小组报告评价中上传的文档"
            >
              {downloadingId === item.id ? (
                <>
                  <i className="fa-solid fa-spinner fa-spin mr-1" />
                  下载中
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
            className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
              isTeacherAuditPassed(item) ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
            }`}
          >
            {auditStatusLabel(item)}
          </span>
          <i
            className={`fa-solid fa-chevron-down text-slate-400 transition-transform ${
              isOpen ? "rotate-180" : ""
            }`}
          />
        </div>
      </button>

      {isOpen && (
        <div className="px-4 pb-4 pt-2 space-y-3 bg-white border-t border-slate-100">
          <p className="text-xs text-slate-400">
            {item.created_at ? new Date(item.created_at).toLocaleString("zh-CN") : ""}
          </p>

          {pendingReview && (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => onApprove(item.id)}
                disabled={busyId === item.id}
                className="bg-green-700 text-white px-4 py-1.5 rounded text-xs hover:bg-green-600 disabled:opacity-60"
              >
                {busyId === item.id ? "处理中..." : "直接通过评分"}
              </button>
              <button
                type="button"
                onClick={() => onInitEdit(item)}
                disabled={busyId === item.id}
                className="border border-red-400 text-red-800 px-4 py-1.5 rounded text-xs hover:bg-red-100 disabled:opacity-60"
              >
                {hasEdits ? "编辑中" : "修改分数"}
              </button>
            </div>
          )}

          {!pendingReview && (
            <button
              type="button"
              onClick={() => onInitEdit(item)}
              className="border border-amber-400 text-amber-800 px-3 py-1 rounded text-xs hover:bg-amber-100"
            >
              编辑分数
            </button>
          )}

          {item.dimension_summary.length > 0 && (
            <div className="overflow-x-auto">
              {needsHighlight && (
                <p className="text-xs font-medium text-red-700 mb-2 flex items-center gap-1">
                  <i className="fa-solid fa-circle-exclamation" />
                  以下 {failedNames.size} 项维度在最大审核轮次内仍未通过审核，请重点核查并修改：
                </p>
              )}
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-slate-500 border-b">
                    <th className="text-left py-2 pr-2">维度</th>
                    <th className="text-left py-2 pr-2">一级指标</th>
                    <th className="text-left py-2 pr-2">均分</th>
                    <th className="text-left py-2">评语摘要</th>
                  </tr>
                </thead>
                <tbody>
                  {item.dimension_summary.map((dim, idx) => {
                    const name = String(dim.dimension_name || "");
                    const edits = editScores[item.id];
                    const isFailed = failedNames.has(name);
                    return (
                      <tr
                        key={idx}
                        className={`border-b border-slate-100 ${isFailed ? "bg-red-50/80" : ""}`}
                      >
                        <td className="py-2 pr-2">
                          {isFailed && (
                            <i
                              className="fa-solid fa-triangle-exclamation text-red-500 mr-1"
                              title="审核未通过"
                            />
                          )}
                          {name}
                        </td>
                        <td className="py-2 pr-2">{String(dim.primary_indicator || "")}</td>
                        <td className="py-2 pr-2">
                          {editable && edits ? (
                            <input
                              type="number"
                              min={1}
                              max={5}
                              step={0.1}
                              value={edits[name] ?? ""}
                              onChange={(e) => onEditChange(item.id, name, e.target.value)}
                              className={`w-16 border rounded px-1 py-0.5 ${
                                isFailed ? "border-red-400 bg-white" : "border-slate-300"
                              }`}
                            />
                          ) : (
                            formatScore(dim.mean)
                          )}
                        </td>
                        <td className="py-2 text-slate-600 whitespace-pre-wrap break-words">
                          {String(dim.summary_comment || "—")}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {hasEdits && (
            <button
              type="button"
              onClick={() => onSaveScores(item, item.dimension_summary)}
              disabled={busyId === item.id}
              className="bg-blue-900 text-white px-4 py-1.5 rounded text-xs disabled:opacity-60"
            >
              {busyId === item.id ? "保存中..." : "保存修改后的分数"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default function TeacherInterventionPanel() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [evaluations, setEvaluations] = useState<TeacherInterventionRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);
  const [toast, setToast] = useState("");
  const [editScores, setEditScores] = useState<Record<number, Record<string, string>>>({});
  const [expandedEvaluations, setExpandedEvaluations] = useState<Record<number, boolean>>({});
  const [expandedProjects, setExpandedProjects] = useState<Record<string, boolean>>({});

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(""), 3000);
  };

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [evalRes, projRes] = await Promise.all([
        teacherInterventionApi.listEvaluations(),
        projectsApi.list(),
      ]);
      setEvaluations(evalRes.data);
      setProjects(projRes.data);
      setExpandedEvaluations((prev) => {
        const next = { ...prev };
        for (const item of evalRes.data) {
          if (next[item.id] === undefined) next[item.id] = false;
        }
        return next;
      });
    } catch {
      showToast("加载介入中心数据失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const projectSections = useMemo((): ProjectSection[] => {
    const byProject = new Map<number | null, TeacherInterventionRecord[]>();
    for (const item of evaluations) {
      const pid = item.project_id ?? null;
      if (!byProject.has(pid)) byProject.set(pid, []);
      byProject.get(pid)!.push(item);
    }

    const knownIds = new Set(projects.map((p) => p.id));
    const sections: ProjectSection[] = projects.map((p) => ({
      key: String(p.id),
      projectId: p.id,
      title: p.title,
      deadline: p.deadline,
      items: byProject.get(p.id) ?? [],
    }));

    for (const [pid, items] of byProject.entries()) {
      if (pid != null && !knownIds.has(pid)) {
        const title = items[0]?.project_title || `项目 #${pid}`;
        sections.push({
          key: String(pid),
          projectId: pid,
          title,
          items,
        });
      }
    }

    const unassigned = byProject.get(null) ?? [];
    if (unassigned.length > 0) {
      sections.push({
        key: "unassigned",
        projectId: null,
        title: "未关联项目",
        items: unassigned,
      });
    }

    return sections;
  }, [evaluations, projects]);

  const handleDownloadReport = async (record: TeacherInterventionRecord) => {
    setDownloadingId(record.id);
    try {
      await groupPblApi.downloadReportFile(record.id, record.filename || "小组报告");
    } catch {
      showToast("报告文档下载失败或文件未存档");
    } finally {
      setDownloadingId(null);
    }
  };

  const handleApprove = async (id: number) => {
    setBusyId(id);
    try {
      const { data } = await teacherInterventionApi.approve(id);
      showToast(data.message || "已直接通过并完成三维度汇总");
      setEditScores((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      await loadAll();
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } };
      showToast(ax.response?.data?.detail || "确认失败");
    } finally {
      setBusyId(null);
    }
  };

  const buildDimensionScores = (
    record: TeacherInterventionRecord,
    dims: GroupPblDimension[]
  ): { dimension_name: string; mean: number }[] | null => {
    const edits = editScores[record.id] || {};
    const dimension_scores = dims
      .map((dim) => {
        const name = String(dim.dimension_name || "");
        const raw = edits[name] ?? String(dim.mean ?? "");
        const mean = parseFloat(raw);
        if (!name || Number.isNaN(mean)) return null;
        return { dimension_name: name, mean };
      })
      .filter(Boolean) as { dimension_name: string; mean: number }[];

    if (!dimension_scores.length) return null;
    return dimension_scores;
  };

  const handleSaveScores = async (
    record: TeacherInterventionRecord,
    dims: GroupPblDimension[]
  ) => {
    const dimension_scores = buildDimensionScores(record, dims);
    if (!dimension_scores) {
      showToast("请填写至少一个有效分数");
      return;
    }

    setBusyId(record.id);
    try {
      await teacherInterventionApi.patchScores(record.id, { dimension_scores });
      showToast("分数已更新，三维度汇总已完成");
      setEditScores((prev) => {
        const next = { ...prev };
        delete next[record.id];
        return next;
      });
      await loadAll();
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } };
      showToast(ax.response?.data?.detail || "保存失败");
    } finally {
      setBusyId(null);
    }
  };

  const initEditRow = (record: TeacherInterventionRecord) => {
    if (editScores[record.id]) return;
    setEditScores((prev) => ({
      ...prev,
      [record.id]: initEditsFromDims(record.dimension_summary),
    }));
  };

  const toggleProject = (key: string) => {
    setExpandedProjects((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const toggleEvaluation = (id: number) => {
    setExpandedEvaluations((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const handleEditChange = (recordId: number, dimName: string, value: string) => {
    setEditScores((prev) => ({
      ...prev,
      [recordId]: {
        ...(prev[recordId] || {}),
        [dimName]: value,
      },
    }));
  };

  const totalPending = evaluations.filter(
    (e) => e.needs_teacher_intervention && !e.teacher_reviewed
  ).length;

  return (
    <div className="space-y-6">
      {toast && (
        <div className="bg-blue-900 text-white px-4 py-2 rounded-lg text-sm">{toast}</div>
      )}

      <section className="bg-white rounded-xl p-6 shadow-sm border border-slate-200 border-t-4 border-t-amber-500">
        <h2 className="text-lg font-bold text-amber-800 border-l-4 border-amber-500 pl-3 mb-1">
          <i className="fa-solid fa-table-list mr-2" />
          小组报告评分 · 十二维度管理
        </h2>
        <p className="text-xs text-slate-400 mb-4 mt-2">
          按项目查看全部小组 PBL 评价（含审核通过与达最大轮次未通过）。展开项目后可查看各组评分详情；未通过项以红色标注。
          项目截止后 30 天内改分将按修改后的 12 维重算三维度，组长于截止 30 天后开放查看后可见。
        </p>

        {loading ? (
          <p className="text-center text-slate-400 py-8 text-sm">加载中...</p>
        ) : projectSections.length === 0 ? (
          <p className="text-center text-slate-400 py-8 text-sm">暂无教师发布的项目</p>
        ) : (
          <div className="space-y-3">
            {totalPending > 0 && (
              <p className="text-xs text-red-700 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
                <i className="fa-solid fa-bell mr-1" />
                全项目共 {totalPending} 条评价待教师确认
              </p>
            )}

            {projectSections.map((section) => {
              const isProjectOpen = expandedProjects[section.key] ?? false;
              const pendingCount = section.items.filter(
                (i) => i.needs_teacher_intervention && !i.teacher_reviewed
              ).length;

              return (
                <div
                  key={section.key}
                  className="border border-slate-200 rounded-xl overflow-hidden shadow-sm"
                >
                  <button
                    type="button"
                    onClick={() => toggleProject(section.key)}
                    className="w-full flex flex-wrap items-center justify-between gap-3 px-5 py-4 text-left bg-slate-50 hover:bg-slate-100 transition-colors"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="font-bold text-slate-800 text-sm flex items-center gap-2">
                        <i className="fa-solid fa-folder-open text-amber-600" />
                        {section.title}
                      </p>
                      <p className="text-xs text-slate-500 mt-1">
                        {section.deadline
                          ? `截止 ${formatDateTime(section.deadline)} · `
                          : ""}
                        {section.items.length} 条小组评价
                        {pendingCount > 0 ? ` · ${pendingCount} 条待确认` : ""}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {pendingCount > 0 && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-red-100 text-red-700">
                          待确认 {pendingCount}
                        </span>
                      )}
                      <i
                        className={`fa-solid fa-chevron-down text-slate-400 transition-transform ${
                          isProjectOpen ? "rotate-180" : ""
                        }`}
                      />
                    </div>
                  </button>

                  {isProjectOpen && (
                    <div className="p-4 space-y-3 bg-white border-t border-slate-100">
                      {section.items.length === 0 ? (
                        <p className="text-center text-slate-400 py-6 text-sm">
                          该项目暂无小组 PBL 评价记录
                        </p>
                      ) : (
                        section.items.map((item) => (
                          <EvaluationRecordCard
                            key={item.id}
                            item={item}
                            isOpen={expandedEvaluations[item.id] ?? false}
                            busyId={busyId}
                            downloadingId={downloadingId}
                            editScores={editScores}
                            onToggle={() => toggleEvaluation(item.id)}
                            onApprove={(id) => void handleApprove(id)}
                            onInitEdit={initEditRow}
                            onSaveScores={(record, dims) => void handleSaveScores(record, dims)}
                            onEditChange={handleEditChange}
                            onDownloadReport={(record) => void handleDownloadReport(record)}
                          />
                        ))
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
