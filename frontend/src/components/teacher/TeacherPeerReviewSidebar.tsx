/** 教师端 — 学生互评侧边栏摘要 */
import type { TeacherPeerReviewRecord } from "../../api/client";

function scoreColor(score: number): string {
  if (score >= 4.5) return "text-emerald-600 bg-emerald-50";
  if (score >= 3.5) return "text-blue-600 bg-blue-50";
  if (score >= 2.5) return "text-amber-600 bg-amber-50";
  return "text-red-600 bg-red-50";
}

interface Props {
  reviews: TeacherPeerReviewRecord[];
  loading?: boolean;
  onViewAll?: () => void;
}

export default function TeacherPeerReviewSidebar({
  reviews,
  loading,
  onViewAll,
}: Props) {
  return (
    <div className="bg-white rounded-xl p-6 shadow-sm border border-slate-200">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-bold text-slate-600">
          <i className="fa-solid fa-users mr-2" />
          学生互评 ({reviews.length})
        </h3>
        {onViewAll && reviews.length > 0 && (
          <button
            type="button"
            onClick={onViewAll}
            className="text-xs text-blue-700 hover:text-blue-900"
          >
            查看全部
          </button>
        )}
      </div>

      {loading ? (
        <p className="text-xs text-slate-400 text-center py-6">
          <i className="fa-solid fa-spinner fa-spin mr-1" />
          加载中…
        </p>
      ) : reviews.length === 0 ? (
        <p className="text-xs text-slate-400 text-center py-6">暂无互评记录</p>
      ) : (
        <div className="space-y-2 max-h-72 overflow-y-auto text-xs">
          {reviews.slice(0, 10).map((r) => (
            <div
              key={r.id}
              className="bg-slate-50 px-3 py-2.5 rounded border border-slate-100"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-medium text-slate-700 truncate">
                    {r.reviewer_name}
                    <span className="text-slate-400 font-normal mx-1">→</span>
                    {r.target_name}
                  </p>
                  <p className="text-slate-400 truncate mt-0.5">
                    {r.group_name ?? "未分组"} · {r.node_name}
                    {r.file_name ? ` · ${r.file_name}` : ""}
                  </p>
                  {r.comment && (
                    <p className="text-slate-500 mt-1 line-clamp-2">&quot;{r.comment}&quot;</p>
                  )}
                </div>
                <span
                  className={`shrink-0 px-2 py-0.5 rounded text-[10px] font-bold ${scoreColor(r.score)}`}
                >
                  {r.score} 分
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
