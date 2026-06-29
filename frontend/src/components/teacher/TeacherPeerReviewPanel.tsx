/** 教师端 — 学生互评完整列表 */
import { useMemo, useState } from "react";
import type { Group, Project, TeacherPeerReviewRecord } from "../../api/client";
import { formatDateTime } from "../../utils/dashboard";

function scoreBadge(score: number): string {
  if (score >= 4.5) return "bg-emerald-100 text-emerald-700";
  if (score >= 3.5) return "bg-blue-100 text-blue-700";
  if (score >= 2.5) return "bg-amber-100 text-amber-700";
  return "bg-red-100 text-red-700";
}

interface Props {
  reviews: TeacherPeerReviewRecord[];
  projects: Project[];
  groups: Group[];
  loading?: boolean;
  selectedProjectId: number | null;
  onProjectChange: (id: number | null) => void;
}

export default function TeacherPeerReviewPanel({
  reviews,
  projects,
  groups,
  loading,
  selectedProjectId,
  onProjectChange,
}: Props) {
  const [groupFilter, setGroupFilter] = useState<string>("");

  const projectGroups = useMemo(
    () =>
      selectedProjectId != null
        ? groups.filter((g) => g.project_id === selectedProjectId)
        : groups,
    [groups, selectedProjectId]
  );

  const filtered = useMemo(() => {
    let list = reviews;
    if (selectedProjectId != null) {
      list = list.filter((r) => r.project_id === selectedProjectId);
    }
    if (groupFilter) {
      list = list.filter((r) => String(r.group_id) === groupFilter);
    }
    return list;
  }, [reviews, selectedProjectId, groupFilter]);

  const stats = useMemo(() => {
    const byGroup = new Set(filtered.map((r) => r.group_id).filter(Boolean));
    const avg =
      filtered.length > 0
        ? (filtered.reduce((s, r) => s + r.score, 0) / filtered.length).toFixed(2)
        : "—";
    return { groupCount: byGroup.size, avg };
  }, [filtered]);

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl p-8 shadow-sm border border-slate-200">
        <h2 className="text-lg font-bold text-blue-900 border-l-4 border-blue-900 pl-3 mb-2">
          <i className="fa-solid fa-users mr-2" />
          学生同伴互评
        </h2>
        <p className="text-sm text-slate-500 mb-6 ml-3">
          实时同步组员 / 组长提交的互评记录，可按项目与小组筛选查看
        </p>

        <div className="flex flex-wrap gap-4 mb-6">
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">项目</label>
            <select
              value={selectedProjectId ?? ""}
              onChange={(e) => {
                onProjectChange(e.target.value ? parseInt(e.target.value, 10) : null);
                setGroupFilter("");
              }}
              className="px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white min-w-[200px]"
            >
              <option value="">全部项目</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-500 mb-1">小组</label>
            <select
              value={groupFilter}
              onChange={(e) => setGroupFilter(e.target.value)}
              className="px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white min-w-[160px]"
            >
              <option value="">全部小组</option>
              {projectGroups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="bg-slate-50 rounded-lg p-4 text-center border border-slate-100">
            <p className="text-2xl font-bold text-blue-900">{filtered.length}</p>
            <p className="text-xs text-slate-500 mt-1">互评条数</p>
          </div>
          <div className="bg-slate-50 rounded-lg p-4 text-center border border-slate-100">
            <p className="text-2xl font-bold text-blue-900">{stats.groupCount}</p>
            <p className="text-xs text-slate-500 mt-1">涉及小组</p>
          </div>
          <div className="bg-slate-50 rounded-lg p-4 text-center border border-slate-100">
            <p className="text-2xl font-bold text-blue-900">{stats.avg}</p>
            <p className="text-xs text-slate-500 mt-1">平均得分</p>
          </div>
        </div>

        {loading ? (
          <p className="text-center text-slate-500 py-16">
            <i className="fa-solid fa-spinner fa-spin mr-2" />
            加载互评数据…
          </p>
        ) : filtered.length === 0 ? (
          <p className="text-center text-slate-400 py-16">暂无互评记录</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 border-b border-slate-200">
                  <th className="text-left py-3 px-2">评价者</th>
                  <th className="text-left py-3 px-2">被评者</th>
                  <th className="text-left py-3 px-2">小组</th>
                  <th className="text-left py-3 px-2">节点 / 成果</th>
                  <th className="text-left py-3 px-2">分数</th>
                  <th className="text-left py-3 px-2">评语</th>
                  <th className="text-left py-3 px-2">时间</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={r.id} className="border-b border-slate-100 hover:bg-slate-50">
                    <td className="py-3 px-2">
                      <p className="font-medium text-slate-800">{r.reviewer_name}</p>
                      <p className="text-xs text-slate-400">{r.reviewer_student_id}</p>
                    </td>
                    <td className="py-3 px-2">
                      <p className="font-medium text-slate-800">{r.target_name}</p>
                      <p className="text-xs text-slate-400">{r.target_student_id}</p>
                    </td>
                    <td className="py-3 px-2 text-slate-600">{r.group_name ?? "—"}</td>
                    <td className="py-3 px-2">
                      <p className="text-slate-700">{r.node_name}</p>
                      <p className="text-xs text-slate-400 truncate max-w-[160px]">
                        {r.file_name ?? "文本提交"}
                      </p>
                    </td>
                    <td className="py-3 px-2">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-xs font-bold ${scoreBadge(r.score)}`}
                      >
                        {r.score}
                      </span>
                    </td>
                    <td className="py-3 px-2 text-slate-600 max-w-[200px]">
                      <p className="line-clamp-2">{r.comment || "—"}</p>
                    </td>
                    <td className="py-3 px-2 text-slate-400 text-xs whitespace-nowrap">
                      {formatDateTime(r.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
