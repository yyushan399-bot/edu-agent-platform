import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import {
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";
import { formatEduAxiosError, formatScore } from "../../api/eduAgent";
import {
  buildPrimaryCards,
  PBL_RADAR_DIMENSIONS,
  resolvePblFeedbackDisplay,
} from "../../utils/pblFeedback";
import { isPastDeadline } from "../../utils/dashboard";
import {
  getGroupPblJob,
  groupPblJobKey,
  isGroupPblRunning,
  runGroupPblEvaluation,
  setGroupPblFileName,
  setGroupPblJobError,
  refreshLeaderPblFromServer,
  subscribeGroupPblJob,
  type GroupPblJobSnapshot,
} from "../../utils/groupPblJob";
import FileDropZone from "./FileDropZone";

interface Props {
  studentId: string;
  sessionId?: string;
  onSessionIdChange?: (sessionId: string) => void;
  llmConfigured: boolean;
  projectId?: number;
  projectDeadline?: string;
}

function loadingLabel(phase: GroupPblJobSnapshot["phase"]) {
  if (phase === "scoring") return "评分中…";
  if (phase === "reviewing") return "审核智能体审核中…";
  return "开始评价";
}

function GroupPblResultView({ result }: { result: Record<string, unknown> }) {
  const primaryCards = buildPrimaryCards(result);
  const finalScore = (result.final_score ?? result.dimension_mean_score) as number | undefined;
  const feedback = resolvePblFeedbackDisplay(result, primaryCards);

  const radarData = PBL_RADAR_DIMENSIONS.map((name) => {
    const card = primaryCards.find((c) => c.title === name);
    const score = Number(card?.score);
    return { subject: name, score: Number.isFinite(score) ? score : 0 };
  });

  const auditPassed = result.audit_passed;
  const auditStatus = String(result.audit_status || "").trim();

  return (
    <div className="space-y-4 text-sm">
      {(auditStatus || auditPassed !== undefined) && (
        <p
          className={`text-xs font-medium px-3 py-2 rounded-lg border ${
            auditPassed === true
              ? "bg-green-50 text-green-800 border-green-100"
              : auditPassed === false
                ? "bg-amber-50 text-amber-800 border-amber-100"
                : "bg-slate-50 text-slate-600 border-slate-100"
          }`}
        >
          <i className="fa-solid fa-shield-halved mr-1" />
          {auditStatus || (auditPassed ? "审核通过" : "审核未通过")}
        </p>
      )}

      <div className="bg-slate-50 rounded-lg p-4 border border-slate-100">
        <p className="text-xs text-slate-500 mb-1">综合分数</p>
        <p className="text-3xl font-bold text-blue-900">{formatScore(finalScore)}</p>
        <p className="text-xs text-slate-400 mt-1">尺度 1.0–5.0</p>
        <div className="grid grid-cols-3 gap-2 mt-4">
          {primaryCards.map((c) => (
            <div key={c.title} className="text-center bg-white rounded-lg py-2 px-1 border border-slate-100">
              <p className="text-[10px] text-slate-500 leading-tight">{c.title}</p>
              <p className="text-lg font-bold text-blue-900">{formatScore(c.score)}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-lg p-4 border border-slate-200">
        <p className="text-xs font-semibold text-slate-600 mb-3">三维度雷达图</p>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="72%">
              <PolarGrid stroke="#cbd5e1" />
              <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11, fill: "#475569" }} />
              <Radar
                name="得分"
                dataKey="score"
                stroke="#1e3a8a"
                fill="#1e3a8a"
                fillOpacity={0.35}
                dot={{ r: 3, fill: "#1e3a8a" }}
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {feedback.mode === "sections" ? (
        <>
          <div className="bg-green-50 rounded-lg p-4 border border-green-100">
            <p className="text-xs font-semibold text-green-800 mb-2">优点</p>
            {feedback.strengths.length > 0 ? (
              <ul className="space-y-1.5 text-slate-700 list-disc list-inside">
                {feedback.strengths.map((item, i) => (
                  <li key={i} className="whitespace-pre-wrap break-words">
                    {item}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-slate-500">暂无</p>
            )}
          </div>

          <div className="bg-amber-50 rounded-lg p-4 border border-amber-100">
            <p className="text-xs font-semibold text-amber-800 mb-2">缺点</p>
            {feedback.weaknesses.length > 0 ? (
              <ul className="space-y-1.5 text-slate-700 list-disc list-inside">
                {feedback.weaknesses.map((item, i) => (
                  <li key={i} className="whitespace-pre-wrap break-words">
                    {item}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-slate-500">暂无</p>
            )}
          </div>

          <div className="bg-blue-50 rounded-lg p-4 border border-blue-100">
            <p className="text-xs font-semibold text-blue-800 mb-2">改进建议</p>
            {feedback.suggestions.length > 0 ? (
              <ul className="space-y-1.5 text-slate-700 list-disc list-inside">
                {feedback.suggestions.map((item, i) => (
                  <li key={i} className="whitespace-pre-wrap break-words">
                    {item}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-slate-500">暂无</p>
            )}
          </div>
        </>
      ) : (
        <div className="bg-slate-50 rounded-lg p-4 border border-slate-200">
          <p className="text-xs font-semibold text-slate-700 mb-2">综合评价</p>
          <p className="text-slate-700 whitespace-pre-wrap break-words leading-relaxed">
            {feedback.text}
          </p>
        </div>
      )}
    </div>
  );
}

export default function GroupEvaluationPanel({
  studentId,
  sessionId,
  onSessionIdChange,
  llmConfigured,
  projectId,
  projectDeadline,
}: Props) {
  const jobKey = groupPblJobKey(studentId, projectId);
  const job = useSyncExternalStore(
    useCallback((cb) => subscribeGroupPblJob(jobKey, cb), [jobKey]),
    () => getGroupPblJob(jobKey),
    () => getGroupPblJob(jobKey)
  );

  const [file, setFile] = useState<File | null>(null);
  const uploadClosed = isPastDeadline(projectDeadline);

  const displayFileName = file?.name || job.fileName;
  const loading = job.loading || isGroupPblRunning(jobKey);
  const result = job.result;
  const scoresVisible = result?.scores_visible !== false;

  useEffect(() => {
    if (!projectId) return;
    void refreshLeaderPblFromServer(jobKey, projectId);
  }, [jobKey, projectId]);

  useEffect(() => {
    if (!projectId || scoresVisible || !result) return;
    const timer = window.setInterval(() => {
      void refreshLeaderPblFromServer(jobKey, projectId);
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [jobKey, projectId, scoresVisible, result]);

  const handleSubmit = async () => {
    if (uploadClosed) {
      setGroupPblJobError(jobKey, "项目已截止，无法上传小组报告");
      return;
    }
    if (!file) {
      setGroupPblJobError(jobKey, "请先上传项目报告");
      return;
    }
    setGroupPblFileName(jobKey, file.name);
    try {
      await runGroupPblEvaluation({
        jobKey,
        file,
        studentId,
        sessionId,
        projectId,
        onSessionIdChange,
      });
    } catch (err) {
      setGroupPblJobError(jobKey, formatEduAxiosError(err));
    }
  };

  return (
    <div className="bg-white rounded-xl p-6 shadow-sm border border-slate-200 space-y-4">
      <div>
        <h2 className="text-lg font-bold text-blue-900 border-l-4 border-blue-900 pl-3">
          小组项目评价
        </h2>
        <p className="text-sm text-slate-500 mt-2">
          整份报告 · 尺度 1.0–5.0 · 含三维度得分、雷达图与文字反馈
        </p>
      </div>

      {uploadClosed && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-800">
          <i className="fa-solid fa-clock mr-1" />
          项目已截止，无法上传或重新评价小组报告。
        </div>
      )}

      {(loading || job.phase !== "idle") && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 text-sm text-blue-900 flex items-center gap-2">
          <i className="fa-solid fa-spinner fa-spin" />
          {job.phase === "scoring" && "正在进行三维度评分，请稍候…"}
          {job.phase === "reviewing" && "评分已完成，报告评分审核智能体正在审核…"}
          {job.phase === "idle" && loading && "处理中…"}
          {displayFileName ? (
            <span className="text-blue-700/80 truncate">· {displayFileName}</span>
          ) : null}
        </div>
      )}

      <FileDropZone
        accept=".pdf,.docx,.txt"
        disabled={loading || uploadClosed}
        onFilesSelected={(files) => setFile(files[0] ?? null)}
        emptyLabel="上传 PDF / DOCX / TXT"
        selectedLabel={displayFileName || undefined}
        iconClass="fa-file-arrow-up"
        className="p-8"
      />

      <button
        type="button"
        onClick={() => void handleSubmit()}
        disabled={loading || !file || !llmConfigured || uploadClosed}
        className="px-6 py-2 bg-blue-900 text-white rounded-lg text-sm font-medium disabled:opacity-60"
      >
        {loading ? loadingLabel(job.phase) : "开始评价"}
      </button>

      {job.error && (
        <pre className="text-xs text-red-600 bg-red-50 p-3 rounded whitespace-pre-wrap">
          {job.error}
        </pre>
      )}

      {job.phase === "reviewing" && loading && (
        <p className="text-xs text-green-700 bg-green-50 border border-green-100 rounded px-3 py-2">
          <i className="fa-solid fa-circle-check mr-1" />
          三维度评分已完成，报告评分审核智能体正在审核…
        </p>
      )}

      {result && (
        <div className="space-y-4 border-t pt-4">
          <h3 className="text-sm font-bold text-slate-700">评价结果</h3>
          {!scoresVisible ? (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-900 text-center">
              小组三维度得分、雷达图与文字反馈将在项目截止 30 天后开放查看。
            </div>
          ) : (
            <GroupPblResultView result={result} />
          )}
        </div>
      )}
    </div>
  );
}
