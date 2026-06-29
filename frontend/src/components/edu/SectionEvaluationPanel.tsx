import { useMemo, useState } from "react";
import { formatEduAxiosError, formatScore, postSectionEvaluation } from "../../api/eduAgent";
import { isPastDeadline } from "../../utils/dashboard";
import { resolveEduSectionSessionId } from "../../utils/eduSession";
import FileDropZone from "./FileDropZone";

const SECTION_NAMES = [
  "文献检索",
  "问题提出",
  "理论分析",
  "数值模拟",
  "实验实施",
  "数据分析",
  "结论生成",
];

interface Props {
  studentId: string;
  sessionId?: string;
  onSessionIdChange?: (sessionId: string) => void;
  llmConfigured: boolean;
  projectDeadline?: string;
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item).trim()).filter(Boolean);
}

function deriveStrengthsWeaknesses(section: Record<string, unknown>): {
  strengths: string[];
  weaknesses: string[];
} {
  const strengths = asStringList(section.strengths);
  const weaknesses = asStringList(section.weaknesses);
  if (strengths.length > 0 || weaknesses.length > 0) {
    return { strengths, weaknesses };
  }

  const details = (section.criterion_details as Array<Record<string, unknown>>) || [];
  const derivedStrengths: string[] = [];
  const derivedWeaknesses: string[] = [];
  for (const row of details) {
    const mean = Number(row.mean);
    const reason = String(row.summary_reason || row.comment || "").trim();
    if (!reason || Number.isNaN(mean)) continue;
    if (mean >= 4.0) derivedStrengths.push(reason);
    else if (mean <= 2.5) derivedWeaknesses.push(reason);
  }
  return { strengths: derivedStrengths, weaknesses: derivedWeaknesses };
}

function SectionFeedbackView({ section }: { section: Record<string, unknown> }) {
  const score = section.total_score ?? section.overall_score;
  const { strengths, weaknesses } = deriveStrengthsWeaknesses(section);
  const suggestions = asStringList(section.suggestions ?? section.revision_suggestions);

  return (
    <div className="space-y-4 text-sm">
      <div className="bg-slate-50 rounded-lg p-4 border border-slate-100">
        <p className="text-xs text-slate-500 mb-1">分数</p>
        <p className="text-2xl font-bold text-blue-900">{formatScore(score as number)}</p>
        <p className="text-xs text-slate-400 mt-1">尺度 1.0–5.0</p>
      </div>

      <div className="bg-green-50 rounded-lg p-4 border border-green-100">
        <p className="text-xs font-semibold text-green-800 mb-2">优点</p>
        {strengths.length > 0 ? (
          <ul className="space-y-1.5 text-slate-700 list-disc list-inside">
            {strengths.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        ) : (
          <p className="text-slate-500">暂无</p>
        )}
      </div>

      <div className="bg-amber-50 rounded-lg p-4 border border-amber-100">
        <p className="text-xs font-semibold text-amber-800 mb-2">缺点</p>
        {weaknesses.length > 0 ? (
          <ul className="space-y-1.5 text-slate-700 list-disc list-inside">
            {weaknesses.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        ) : (
          <p className="text-slate-500">暂无</p>
        )}
      </div>

      <div className="bg-blue-50 rounded-lg p-4 border border-blue-100">
        <p className="text-xs font-semibold text-blue-800 mb-2">改进建议</p>
        {suggestions.length > 0 ? (
          <ul className="space-y-1.5 text-slate-700 list-disc list-inside">
            {suggestions.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        ) : (
          <p className="text-slate-500">暂无</p>
        )}
      </div>
    </div>
  );
}

export default function SectionEvaluationPanel({
  studentId,
  sessionId,
  onSessionIdChange,
  llmConfigured,
  projectDeadline,
}: Props) {
  const [file, setFile] = useState<File | null>(null);
  const uploadClosed = isPastDeadline(projectDeadline);
  const [sectionTarget, setSectionTarget] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [activeSection, setActiveSection] = useState("");

  const sectionResults = (result?.section_results as Array<Record<string, unknown>>) || [];

  const overallScore = useMemo(() => {
    if (!result) return null;
    return (result.overall_score ?? result.final_score) as number | null;
  }, [result]);

  const currentSection = useMemo(() => {
    if (!sectionResults.length) return null;
    if (!activeSection) return sectionResults[0];
    return sectionResults.find((s) => s.section_name === activeSection) || sectionResults[0];
  }, [sectionResults, activeSection]);

  const handleSubmit = async () => {
    if (uploadClosed) {
      setError("项目已截止，无法上传报告");
      return;
    }
    if (!file) {
      setError("请先上传报告");
      return;
    }
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const activeSessionId = await resolveEduSectionSessionId(studentId, sessionId ?? "");
      if (activeSessionId && activeSessionId !== sessionId) {
        onSessionIdChange?.(activeSessionId);
      }
      const data = await postSectionEvaluation({
        file,
        sectionName: sectionTarget,
        enableReview: true,
        scoringTimes: 10,
        reviewRounds: 3,
        studentId,
        sessionId: activeSessionId,
      });
      setResult(data as Record<string, unknown>);
      const names = ((data.section_results as Array<Record<string, unknown>>) || [])
        .map((s) => s.section_name)
        .filter(Boolean) as string[];
      setActiveSection(names[0] || "");
    } catch (err) {
      setError(formatEduAxiosError(err));
    } finally {
      setLoading(false);
    }
  };

  const fallbackSection = useMemo(() => {
    if (currentSection) return currentSection;
    if (!result) return null;
    return {
      total_score: overallScore,
      strengths: result.strengths,
      weaknesses: result.weaknesses,
      suggestions: result.suggestions ?? result.revision_suggestions,
    } as Record<string, unknown>;
  }, [currentSection, result, overallScore]);

  return (
    <div className="bg-white rounded-xl p-6 shadow-sm border border-slate-200 space-y-4">
      <div>
        <h2 className="text-lg font-bold text-blue-900 border-l-4 border-blue-900 pl-3">
          个人终结性评价
        </h2>
        <p className="text-sm text-slate-500 mt-2">按章节切分并加权评价（1.0–5.0）</p>
      </div>

      {uploadClosed && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-800">
          <i className="fa-solid fa-clock mr-1" />
          项目已截止，无法上传或重新评价个人终结性报告。
        </div>
      )}

      <FileDropZone
        accept=".pdf,.docx,.txt"
        disabled={loading || uploadClosed}
        onFilesSelected={(files) => setFile(files[0] ?? null)}
        emptyLabel="上传 PDF / DOCX / TXT"
        selectedLabel={file?.name}
        iconClass="fa-file-lines"
        className="p-8"
      />

      <div className="flex flex-wrap gap-4 text-sm items-center">
        <select
          value={sectionTarget}
          onChange={(e) => setSectionTarget(e.target.value)}
          className="border border-slate-300 rounded-lg px-3 py-2"
        >
          <option value="">全部章节（自动切分）</option>
          {SECTION_NAMES.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </div>

      <button
        type="button"
        onClick={() => void handleSubmit()}
        disabled={loading || !file || !llmConfigured || uploadClosed}
        className="px-6 py-2 bg-blue-900 text-white rounded-lg text-sm font-medium disabled:opacity-60"
      >
        {loading ? "评价中…" : "开始评价"}
      </button>

      {error && <pre className="text-xs text-red-600 bg-red-50 p-3 rounded whitespace-pre-wrap">{error}</pre>}

      {result && fallbackSection && (
        <div className="space-y-4 border-t pt-4">
          {sectionResults.length > 1 && (
            <>
              {overallScore != null && (
                <p className="text-sm text-slate-600">
                  综合分数 {formatScore(overallScore)}
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                {sectionResults.map((s) => (
                  <button
                    key={String(s.section_name)}
                    type="button"
                    onClick={() => setActiveSection(String(s.section_name))}
                    className={`text-xs px-3 py-1.5 rounded-full border ${
                      activeSection === s.section_name
                        ? "bg-blue-900 text-white border-blue-900"
                        : "bg-white text-slate-600 border-slate-300"
                    }`}
                  >
                    {String(s.section_name)} · {formatScore(s.total_score as number)}
                  </button>
                ))}
              </div>
            </>
          )}

          {sectionResults.length === 1 && (
            <p className="text-sm font-medium text-slate-700">
              {String(sectionResults[0].section_name || "评价结果")}
            </p>
          )}

          <SectionFeedbackView section={fallbackSection} />
        </div>
      )}
    </div>
  );
}
