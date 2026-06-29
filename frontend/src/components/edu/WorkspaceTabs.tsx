import type { ReactNode } from "react";

export type WorkspaceTab = "project" | "ai" | "peer-review";

interface Props {
  active: WorkspaceTab;
  onChange: (tab: WorkspaceTab) => void;
  roleLabel: string;
}

export function WorkspaceTabBar({ active, onChange, roleLabel }: Props) {
  return (
    <div className="flex flex-wrap gap-2 mb-6">
      <button
        type="button"
        onClick={() => onChange("project")}
        className={`px-5 py-2 rounded-lg text-sm font-medium transition-colors ${
          active === "project"
            ? "bg-blue-900 text-white shadow-sm"
            : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
        }`}
      >
        <i className="fa-solid fa-timeline mr-2" />
        {roleLabel} · 项目节点
      </button>
      <button
        type="button"
        onClick={() => onChange("ai")}
        className={`px-5 py-2 rounded-lg text-sm font-medium transition-colors ${
          active === "ai"
            ? "bg-blue-900 text-white shadow-sm"
            : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
        }`}
      >
        <i className="fa-solid fa-robot mr-2" />
        AI 智能评价
      </button>
      <button
        type="button"
        onClick={() => onChange("peer-review")}
        className={`px-5 py-2 rounded-lg text-sm font-medium transition-colors ${
          active === "peer-review"
            ? "bg-blue-900 text-white shadow-sm"
            : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
        }`}
      >
        <i className="fa-solid fa-users mr-2" />
        同伴互评
      </button>
    </div>
  );
}

export function WorkspaceBody({
  active,
  projectContent,
  aiContent,
  peerReviewContent,
}: {
  active: WorkspaceTab;
  projectContent: ReactNode;
  aiContent: ReactNode;
  peerReviewContent?: ReactNode;
}) {
  if (active === "project") return projectContent;
  if (active === "ai") return aiContent;
  return peerReviewContent ?? null;
}
