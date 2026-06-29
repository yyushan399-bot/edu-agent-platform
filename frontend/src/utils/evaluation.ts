export const DIM_LABELS: Record<string, string> = {
  theory: "理论维度",
  practice: "实践维度",
  data: "数据维度",
  literature: "文献维度",
};

export const SUB_INDICATOR_LABELS: Record<string, string> = {
  concept_accuracy: "概念准确性",
  logic_integrity: "逻辑完整性",
  theory_transfer: "理论迁移",
  design_completeness: "设计完整性",
  operational_standard: "操作规范性",
  problem_solving: "问题解决",
  data_collection: "数据采集",
  data_analysis: "数据分析",
  visualization: "可视化",
  lit_understanding: "文献理解",
  viewpoint_consistency: "观点一致性",
  critical_thinking: "批判性思维",
  innovation_extension: "创新延伸",
};

export function dimLabel(key: string): string {
  return DIM_LABELS[key] ?? key;
}

export function indicatorLabel(key: string): string {
  return SUB_INDICATOR_LABELS[key] ?? key.replace(/_/g, " ");
}

export function scoreColor(score: number): string {
  if (score >= 4) return "text-green-600 bg-green-50 border-green-200";
  if (score >= 3) return "text-amber-600 bg-amber-50 border-amber-200";
  return "text-red-600 bg-red-50 border-red-200";
}

export function scoreBarColor(score: number): string {
  if (score >= 4) return "bg-green-500";
  if (score >= 3) return "bg-amber-500";
  return "bg-red-500";
}

export function roleHomePath(role: string): string {
  const map: Record<string, string> = {
    teacher: "/teacher",
    admin: "/admin",
    group_leader: "/leader",
    group_member: "/member",
  };
  return map[role] ?? "/login";
}

export function formatScore(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(2);
}
