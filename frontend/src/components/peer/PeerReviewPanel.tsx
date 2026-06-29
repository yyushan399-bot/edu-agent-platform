/**
 * 同伴互评面板 — 仅评价同组成员的「AI 作业分析」提交
 */

import { useCallback, useEffect, useState } from "react";
import {
  aiAnalyzeSubmissionsApi,
  peerReviewApi,
  type PeerReviewAssignment,
  type PeerAssessmentResult,
} from "../../api/client";
import { useAuth } from "../../api/auth";
import { getFileIconClass } from "../../utils/dashboard";

function itemKey(item: PeerReviewAssignment): string {
  return `ai-${item.ai_analyze_submission_id}`;
}

function StarRating({
  value,
  onChange,
  disabled,
}: {
  value: number;
  onChange: (v: number) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          disabled={disabled}
          onClick={() => onChange(star)}
          className={`text-xl transition-colors ${
            disabled ? "cursor-not-allowed" : "cursor-pointer hover:scale-110"
          }`}
        >
          <i
            className={`fa-star ${
              star <= value ? "fa-solid text-amber-400" : "fa-regular text-slate-300"
            }`}
          />
        </button>
      ))}
    </div>
  );
}

function HistoryBadge({ record }: { record: PeerAssessmentResult }) {
  return (
    <div className="flex items-center gap-2 text-xs bg-green-50 border border-green-200 text-green-700 px-3 py-1.5 rounded-full">
      <i className="fa-solid fa-circle-check" />
      已评价 · {record.score} 分
      {record.comment
        ? ` · "${record.comment.slice(0, 20)}${record.comment.length > 20 ? "…" : ""}"`
        : ""}
    </div>
  );
}

function ReviewForm({
  assignment,
  onSubmit,
  submitting,
  existing,
}: {
  assignment: PeerReviewAssignment;
  onSubmit: (a: PeerReviewAssignment, score: number, comment: string) => Promise<void>;
  submitting: boolean;
  existing: PeerAssessmentResult | null;
}) {
  const [score, setScore] = useState(3);
  const [comment, setComment] = useState("");

  if (existing) {
    return (
      <div className="mt-3 pt-3 border-t border-slate-100">
        <HistoryBadge record={existing} />
      </div>
    );
  }

  return (
    <div className="mt-4 pt-4 border-t border-slate-100 space-y-3">
      <div>
        <label className="block text-xs font-semibold text-slate-500 mb-1.5">评分</label>
        <StarRating value={score} onChange={setScore} disabled={submitting} />
        <p className="text-xs text-slate-400 mt-1">1 分 = 差，5 分 = 优秀</p>
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-500 mb-1.5">
          评语 <span className="text-slate-300 font-normal">（可选）</span>
        </label>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="请给出你对这份 AI 作业分析的具体建议…"
          rows={3}
          disabled={submitting}
          className="w-full p-2.5 border border-slate-300 rounded text-sm outline-none focus:border-blue-500 resize-none disabled:bg-slate-100"
        />
      </div>
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => void onSubmit(assignment, score, comment.trim())}
          disabled={submitting}
          className="px-5 py-2 bg-blue-900 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-60 flex items-center gap-2"
        >
          {submitting ? (
            <>
              <i className="fa-solid fa-spinner fa-spin" />
              提交中…
            </>
          ) : (
            <>
              <i className="fa-solid fa-paper-plane" />
              提交互评
            </>
          )}
        </button>
      </div>
    </div>
  );
}

export default function PeerReviewPanel({ projectId }: { projectId: number }) {
  const { user } = useAuth();
  const [assignments, setAssignments] = useState<PeerReviewAssignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [submittingId, setSubmittingId] = useState<number | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    if (!user || !projectId || Number.isNaN(projectId)) return;
    setLoading(true);
    setError("");
    try {
      const { data } = await peerReviewApi.listAssignments(projectId);
      setAssignments(data.items);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "加载待评列表失败";
      setError(String(detail));
    } finally {
      setLoading(false);
    }
  }, [user, projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSubmit = async (
    assignment: PeerReviewAssignment,
    score: number,
    comment: string
  ) => {
    setSubmittingId(assignment.ai_analyze_submission_id);
    try {
      const { data } = await peerReviewApi.submit({
        ai_analyze_submission_id: assignment.ai_analyze_submission_id,
        score,
        comment: comment || undefined,
      });
      setAssignments((prev) =>
        prev.map((item) =>
          item.ai_analyze_submission_id === assignment.ai_analyze_submission_id
            ? { ...item, my_review: data.peer_assessment }
            : item
        )
      );
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "提交失败，请重试";
      alert(detail);
    } finally {
      setSubmittingId(null);
    }
  };

  const handleDownload = async (item: PeerReviewAssignment) => {
    if (!item.has_file) return;
    setDownloadingId(item.ai_analyze_submission_id);
    try {
      await aiAnalyzeSubmissionsApi.downloadFile(
        item.ai_analyze_submission_id,
        item.file_name || "作业文件"
      );
    } catch {
      alert("文件下载失败，请重试");
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <section className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-blue-900 border-l-4 border-blue-900 pl-3">
            <i className="fa-solid fa-users mr-2" />
            同伴互评
          </h2>
          <p className="text-sm text-slate-500 mt-1 ml-3">
            仅评价同组成员在「AI 作业分析」中提交并分析过的报告（每人每份仅可评价一次）
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="text-sm text-blue-700 hover:text-blue-900 border border-blue-200 px-3 py-1.5 rounded-lg bg-blue-50 flex items-center gap-1.5"
        >
          <i className="fa-solid fa-rotate" />
          刷新
        </button>
      </div>

      {loading && (
        <div className="bg-white rounded-xl p-12 text-center shadow-sm border border-slate-200">
          <i className="fa-solid fa-spinner fa-spin text-2xl text-slate-300 mb-3" />
          <p className="text-sm text-slate-500">加载待评列表…</p>
        </div>
      )}

      {error && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-lg p-4 text-sm">
          <i className="fa-solid fa-circle-exclamation mr-2" />
          {error}
        </div>
      )}

      {!loading && !error && assignments.length === 0 && (
        <div className="bg-white rounded-xl p-12 text-center shadow-sm border border-dashed border-slate-300">
          <i className="fa-solid fa-inbox text-4xl text-slate-300 mb-3" />
          <p className="text-slate-500 font-medium">暂无待评作业分析</p>
          <p className="text-slate-400 text-sm mt-1">
            同组成员在「AI 智能评价 → AI 作业分析」中点击「提交并分析」后，会出现在此列表
          </p>
        </div>
      )}

      {!loading && assignments.length > 0 && (
        <div className="space-y-4">
          {assignments.map((item) => {
            const existing = item.my_review ?? null;
            const id = item.ai_analyze_submission_id;
            const isSubmitting = submittingId === id;
            const isExpanded = expandedId === id;

            return (
              <div
                key={itemKey(item)}
                className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden"
              >
                <button
                  type="button"
                  onClick={() => setExpandedId(isExpanded ? null : id)}
                  className="w-full flex items-center justify-between p-5 text-left hover:bg-slate-50 transition-colors"
                >
                  <div className="flex items-center gap-4 min-w-0">
                    <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center shrink-0">
                      <i className="fa-solid fa-user-graduate text-blue-900" />
                    </div>
                    <div className="min-w-0">
                      <p className="font-semibold text-slate-800 truncate">{item.student_name}</p>
                      <p className="text-xs text-slate-500 mt-0.5">
                        <span className="bg-slate-100 px-2 py-0.5 rounded mr-2">{item.node_name}</span>
                        {item.has_file && item.file_name ? (
                          <span className="inline-flex items-center gap-1">
                            <i className={getFileIconClass(item.file_name)} />
                            {item.file_name}
                          </span>
                        ) : (
                          <span className="text-slate-400">作业分析记录</span>
                        )}
                      </p>
                      {(item.self_score != null || item.ai_total_score != null) && (
                        <p className="text-xs text-slate-400 mt-0.5">
                          {item.self_score != null && `自评 ${item.self_score} 分`}
                          {item.self_score != null && item.ai_total_score != null && " · "}
                          {item.ai_total_score != null && `AI 评 ${item.ai_total_score} 分`}
                        </p>
                      )}
                      {item.submit_time && (
                        <p className="text-xs text-slate-400 mt-0.5">
                          <i className="fa-regular fa-clock mr-1" />
                          {new Date(item.submit_time).toLocaleString("zh-CN")}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    {existing && <HistoryBadge record={existing} />}
                    <i
                      className={`fa-solid fa-chevron-down text-slate-400 transition-transform ${
                        isExpanded ? "rotate-180" : ""
                      }`}
                    />
                  </div>
                </button>

                {isExpanded && (
                  <div className="px-5 pb-5">
                    {item.text_preview && (
                      <div className="mb-3 p-3 bg-slate-50 rounded-lg border border-slate-100 text-sm text-slate-600">
                        <p className="text-xs font-semibold text-slate-500 mb-1">内容预览</p>
                        <p className="whitespace-pre-wrap line-clamp-4">{item.text_preview}</p>
                      </div>
                    )}
                    {item.has_file && (
                      <div className="mb-3 p-3 bg-slate-50 rounded-lg border border-slate-100 text-sm">
                        <button
                          type="button"
                          onClick={() => void handleDownload(item)}
                          disabled={downloadingId === id}
                          className="text-blue-700 hover:text-blue-900 flex items-center gap-2 disabled:opacity-60"
                        >
                          {downloadingId === id ? (
                            <i className="fa-solid fa-spinner fa-spin" />
                          ) : (
                            <i className="fa-solid fa-download" />
                          )}
                          下载查看作业文件
                        </button>
                      </div>
                    )}
                    <ReviewForm
                      assignment={item}
                      onSubmit={handleSubmit}
                      submitting={isSubmitting}
                      existing={existing}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
