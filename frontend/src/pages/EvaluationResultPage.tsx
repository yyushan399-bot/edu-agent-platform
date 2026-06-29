/** 评估结果展示页 —— 雷达图 + 维度卡片 + 元评估报告 */
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { useAuth } from "../api/auth";
import {
  evaluationsApi,
  type Evaluation,
  type EvaluationDetail,
} from "../api/client";
import { fileNameFromPath, formatDeadline } from "../utils/dashboard";
import {
  dimLabel,
  formatScore,
  indicatorLabel,
  roleHomePath,
  scoreBarColor,
  scoreColor,
} from "../utils/evaluation";

export default function EvaluationResultPage() {
  const { submissionId } = useParams<{ submissionId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [detail, setDetail] = useState<EvaluationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const id = parseInt(submissionId ?? "", 10);

  useEffect(() => {
    if (!submissionId || Number.isNaN(id)) {
      setError("无效的提交 ID");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    evaluationsApi
      .getDetail(id)
      .then((r) => setDetail(r.data))
      .catch(() => setError("无法加载评估结果，可能尚未评估或无权查看"))
      .finally(() => setLoading(false));
  }, [submissionId, id]);

  const radarData = useMemo(() => {
    if (!detail?.evaluations.length) return [];
    return detail.evaluations.map((ev) => ({
      subject: dimLabel(ev.dim_key),
      score: ev.dimension_score ?? 0,
      fullMark: 5,
    }));
  }, [detail]);

  const backPath = user ? roleHomePath(user.role) : "/login";

  if (loading) {
    return (
      <PageShell backPath={backPath}>
        <p className="text-center text-slate-500 py-20">
          <i className="fa-solid fa-spinner fa-spin mr-2" />
          加载评估结果...
        </p>
      </PageShell>
    );
  }

  if (error || !detail) {
    return (
      <PageShell backPath={backPath}>
        <div className="max-w-lg mx-auto text-center py-20">
          <i className="fa-solid fa-circle-exclamation text-4xl text-amber-500 mb-4" />
          <p className="text-slate-600 mb-6">{error || "未找到评估数据"}</p>
          <Link
            to={backPath}
            className="text-blue-700 hover:underline text-sm"
          >
            返回控制台
          </Link>
        </div>
      </PageShell>
    );
  }

  const { submission, evaluations, meta_report } = detail;
  const totalScore = meta_report?.total_score;
  const hasEvaluations = evaluations.length > 0;

  return (
    <PageShell backPath={backPath}>
      <div className="max-w-5xl mx-auto space-y-8">
        {/* 提交概览 */}
        <section className="bg-white rounded-xl p-6 shadow-sm border border-slate-200">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">
                评估报告
              </p>
              <h1 className="text-2xl font-bold text-blue-900">
                {submission.node?.name ?? `节点 #${submission.node_id}`}
              </h1>
              <p className="text-sm text-slate-500 mt-2">
                提交时间：
                {new Date(submission.submitted_at).toLocaleString("zh-CN")}
                {submission.node?.deadline && (
                  <span className="ml-3">
                    截止 {formatDeadline(submission.node.deadline)}
                  </span>
                )}
              </p>
              {(submission.file_path || submission.text_content) && (
                <p className="text-sm text-slate-600 mt-2 line-clamp-2">
                  {fileNameFromPath(submission.file_path) ||
                    submission.text_content?.slice(0, 120)}
                </p>
              )}
            </div>
            {totalScore != null && (
              <div className="text-center bg-blue-50 border border-blue-200 rounded-xl px-8 py-4">
                <p className="text-xs font-semibold text-blue-600 mb-1">综合得分</p>
                <p className="text-4xl font-bold text-blue-900">
                  {formatScore(totalScore)}
                </p>
                <p className="text-xs text-slate-400 mt-1">满分 5.0</p>
              </div>
            )}
          </div>
        </section>

        {!hasEvaluations ? (
          <section className="bg-amber-50 border border-amber-200 rounded-xl p-8 text-center">
            <i className="fa-solid fa-hourglass-half text-3xl text-amber-500 mb-3" />
            <p className="text-amber-800 font-medium">该提交尚未完成智能体评估</p>
            <p className="text-sm text-amber-700 mt-1">
              请等待教师触发评估，或稍后刷新本页
            </p>
          </section>
        ) : (
          <>
            {/* 雷达图 */}
            {radarData.length >= 2 && (
              <section className="bg-white rounded-xl p-6 shadow-sm border border-slate-200">
                <h2 className="text-lg font-bold text-blue-900 border-l-4 border-blue-900 pl-3 mb-6">
                  <i className="fa-solid fa-chart-radar mr-2" />
                  多维度能力雷达
                </h2>
                <div className="h-80 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="75%">
                      <PolarGrid stroke="#e2e8f0" />
                      <PolarAngleAxis
                        dataKey="subject"
                        tick={{ fill: "#475569", fontSize: 12 }}
                      />
                      <PolarRadiusAxis
                        angle={90}
                        domain={[0, 5]}
                        tick={{ fill: "#94a3b8", fontSize: 10 }}
                      />
                      <Radar
                        name="得分"
                        dataKey="score"
                        stroke="#1e3a8a"
                        fill="#3b82f6"
                        fillOpacity={0.35}
                        strokeWidth={2}
                      />
                      <Tooltip
                        formatter={(value) => {
                          const n = typeof value === "number" ? value : Number(value);
                          return [`${Number.isNaN(n) ? "—" : n.toFixed(2)} 分`, "维度得分"];
                        }}
                      />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              </section>
            )}

            {/* 维度分数卡片 */}
            <section className="space-y-4">
              <h2 className="text-lg font-bold text-blue-900 border-l-4 border-blue-900 pl-3">
                <i className="fa-solid fa-layer-group mr-2" />
                各维度形成性评价
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {evaluations.map((ev) => (
                  <DimensionCard key={ev.id} evaluation={ev} />
                ))}
              </div>
            </section>
          </>
        )}

        {/* 元评估报告 */}
        {meta_report?.report_content && (
          <section className="bg-white rounded-xl p-6 shadow-sm border border-slate-200">
            <h2 className="text-lg font-bold text-blue-900 border-l-4 border-blue-900 pl-3 mb-6">
              <i className="fa-solid fa-file-lines mr-2" />
              元评估综合报告
            </h2>
            <div className="markdown-report text-sm text-slate-700 leading-relaxed space-y-3 [&_h1]:text-xl [&_h1]:font-bold [&_h2]:text-lg [&_h2]:font-bold [&_h3]:font-semibold [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_strong]:font-semibold [&_p]:mb-2">
              <ReactMarkdown>{meta_report.report_content}</ReactMarkdown>
            </div>
          </section>
        )}
      </div>
    </PageShell>
  );
}

function DimensionCard({ evaluation }: { evaluation: Evaluation }) {
  const score = evaluation.dimension_score;
  const scores = evaluation.scores ?? {};
  const feedbacks = evaluation.feedbacks ?? {};
  const indicators = Object.keys(scores);

  return (
    <article className="bg-white rounded-xl p-5 shadow-sm border border-slate-200">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-bold text-slate-800">{dimLabel(evaluation.dim_key)}</h3>
        {score != null && (
          <span
            className={`text-lg font-bold px-3 py-1 rounded-lg border ${scoreColor(score)}`}
          >
            {formatScore(score)}
          </span>
        )}
      </div>

      {evaluation.summary && (
        <p className="text-sm text-slate-600 bg-slate-50 rounded-lg p-3 mb-4 border border-slate-100">
          {evaluation.summary}
        </p>
      )}

      {indicators.length > 0 && (
        <div className="space-y-3">
          {indicators.map((key) => {
            const val = scores[key];
            const pct = typeof val === "number" ? (val / 5) * 100 : 0;
            return (
              <div key={key}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="font-medium text-slate-600">
                    {indicatorLabel(key)}
                  </span>
                  <span className="font-bold text-slate-700">{val ?? "—"} / 5</span>
                </div>
                <div className="h-1.5 bg-slate-200 rounded-full overflow-hidden mb-1">
                  <div
                    className={`h-full rounded-full transition-all ${scoreBarColor(typeof val === "number" ? val : 0)}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                {feedbacks[key] && (
                  <p className="text-xs text-slate-500">{feedbacks[key]}</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </article>
  );
}

function PageShell({
  backPath,
  children,
}: {
  backPath: string;
  children: React.ReactNode;
}) {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white shadow-sm px-6 py-4 border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-5xl mx-auto flex items-center gap-4">
          <button
            onClick={() => navigate(backPath)}
            className="text-slate-500 hover:text-blue-700 text-sm flex items-center gap-1"
          >
            <i className="fa-solid fa-arrow-left" />
            返回
          </button>
          <h1 className="text-lg font-bold text-blue-900 flex items-center gap-2">
            <i className="fa-solid fa-chart-pie" />
            评估结果
          </h1>
        </div>
      </header>
      <main className="px-6 py-8">{children}</main>
    </div>
  );
}
