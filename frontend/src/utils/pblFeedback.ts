/** 小组 PBL 评价反馈展示：仅展示三一级指标，过滤 12 维与缩写标签 */

const PRIMARY_FEEDBACK_NAMES = ["创造性思维", "批判性思维", "问题解决能力"] as const;

const SECONDARY_DIMENSION_NAMES = new Set([
  "问题提出",
  "方案新颖性",
  "创新表征",
  "创新表达",
  "问题界定",
  "方案建构",
  "方案实施",
  "反思调节",
  "证据分析",
  "数据分析",
  "逻辑推演",
  "局限性评价",
]);

const BOILERPLATE_PATTERNS: RegExp[] = [
  /该一级指标由相关二级指标等权汇总得到/,
  /符合量规[\d.]*分(?:的)?描述/,
  /建议结合二级指标中的薄弱项进一步核查/,
  /后续可围绕.+下属二级指标逐项补强/,
  /但当前二级指标评价文本不足/,
  /保持优势表现，同时针对低分或评价较弱的环节进行有针对性的修改/,
];

export function isBoilerplateFeedback(text: string): boolean {
  const t = text.trim();
  if (!t) return true;
  return BOILERPLATE_PATTERNS.some((p) => p.test(t));
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item).trim()).filter(Boolean);
}

function parsePrimaryLine(line: string): { name: string; body: string } | null {
  const m = line.trim().match(/^([^：:]+)[：:]\s*(.*)$/s);
  if (!m) return null;
  const name = canonicalPrimaryFeedbackName(m[1]);
  if (!(PRIMARY_FEEDBACK_NAMES as readonly string[]).includes(name)) return null;
  const body = m[2].trim();
  if (!body) return null;
  return { name, body };
}

/** 同一一级指标只保留一条，优先保留更完整的内容 */
function pickBetterPrimaryLine(a: string, b: string): string {
  const pa = parsePrimaryLine(a);
  const pb = parsePrimaryLine(b);
  if (!pa) return b;
  if (!pb) return a;
  if (pa.body === pb.body) return a;
  if (pa.body.includes(pb.body)) return a;
  if (pb.body.includes(pa.body)) return b;
  return pa.body.length >= pb.body.length ? a : b;
}

/** 每个一级指标在列表中最多出现一次，并按固定顺序排列 */
function dedupeByPrimaryDimension(items: string[]): string[] {
  const byName = new Map<string, string>();
  for (const raw of items) {
    const parsed = parsePrimaryLine(raw);
    if (!parsed || isBoilerplateFeedback(parsed.body)) continue;
    const line = `${parsed.name}：${parsed.body}`;
    const existing = byName.get(parsed.name);
    byName.set(parsed.name, existing ? pickBetterPrimaryLine(existing, line) : line);
  }
  return PRIMARY_FEEDBACK_NAMES.map((name) => byName.get(name)).filter(Boolean) as string[];
}

function uniqueMeaningful(items: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of items) {
    const t = raw.trim();
    if (!t || isBoilerplateFeedback(t) || seen.has(t)) continue;
    seen.add(t);
    out.push(t);
  }
  return dedupeByPrimaryDimension(out);
}

function withPrimaryPrefix(name: string, text: string): string {
  const t = text.trim();
  if (!t) return "";
  const label = canonicalPrimaryFeedbackName(name);
  if (!label) return t;
  if (t.startsWith(`${label}：`) || t.startsWith(`${label}:`)) return t;
  return `${label}：${t}`;
}

/** 雷达图/卡片短标题（「问题解决能力」→「问题解决」） */
export function normalizePrimaryIndicatorTitle(name: string): string {
  const n = name.trim();
  if (n === "问题解决能力" || n === "问题解决") return "问题解决";
  return n;
}

/** 文字反馈区统一使用完整一级指标名 */
export function canonicalPrimaryFeedbackName(name: string): string {
  const n = name.trim();
  if (n === "问题解决" || n === "问题解决能力") return "问题解决能力";
  if (n === "创造性思维" || n === "批判性思维") return n;
  return n;
}

function containsSecondaryDimensionText(text: string): boolean {
  const t = text.trim();
  if (!t) return false;
  for (const dim of SECONDARY_DIMENSION_NAMES) {
    if (t.includes(`${dim}：`) || t.includes(`${dim}:`)) return true;
  }
  return false;
}

function isAllowedPrimaryFeedbackLine(line: string): boolean {
  const t = line.trim();
  if (!t || containsSecondaryDimensionText(t)) return false;
  const m = t.match(/^([^：:]+)[：:]/);
  if (!m) return false;
  const prefix = canonicalPrimaryFeedbackName(m[1]);
  return (PRIMARY_FEEDBACK_NAMES as readonly string[]).includes(prefix);
}

function normalizePrimaryFeedbackLine(line: string): string {
  const t = line.trim();
  const m = t.match(/^([^：:]+)[：:]\s*(.*)$/s);
  if (!m) return t;
  const label = canonicalPrimaryFeedbackName(m[1]);
  const body = m[2].trim();
  if (!body || containsSecondaryDimensionText(body)) return "";
  return `${label}：${body}`;
}

function filterPrimaryFeedbackLines(items: string[]): string[] {
  const out: string[] = [];
  for (const raw of items) {
    for (const part of raw.split(/[；;\n]/)) {
      const line = part.trim();
      if (!line || !isAllowedPrimaryFeedbackLine(line)) continue;
      const normalized = normalizePrimaryFeedbackLine(line);
      if (normalized) out.push(normalized);
    }
  }
  return out;
}

function pickPrimaryFieldText(...fields: string[]): string {
  for (const field of fields) {
    const t = field.trim();
    if (t && !containsSecondaryDimensionText(t) && !isBoilerplateFeedback(t)) {
      return t;
    }
  }
  return "";
}

export const PBL_RADAR_DIMENSIONS = ["创造性思维", "批判性思维", "问题解决"] as const;

export function buildPrimaryCards(result: Record<string, unknown>) {
  const primary = (result.primary_indicator_summary as Array<Record<string, unknown>>) || [];
  if (primary.length) {
    return primary.map((item) => ({
      title: normalizePrimaryIndicatorTitle(String(item.primary_indicator_name || "一级指标")),
      score: item.mean as number | undefined,
      comment: String(item.summary_comment || ""),
      advantages: String(item.advantages || ""),
      disadvantages: String(item.disadvantages || ""),
      suggestions: String(item.improvement_suggestions || ""),
    }));
  }
  const c = result.creativity as Record<string, unknown> | undefined;
  const cr = result.critical as Record<string, unknown> | undefined;
  const p = result.problemsolving as Record<string, unknown> | undefined;
  return [
    {
      title: "创造性思维",
      score: c?.score as number | undefined,
      comment: String(c?.feedback || ""),
      advantages: "",
      disadvantages: "",
      suggestions: "",
    },
    {
      title: "批判性思维",
      score: cr?.score as number | undefined,
      comment: String(cr?.feedback || ""),
      advantages: "",
      disadvantages: "",
      suggestions: "",
    },
    {
      title: "问题解决",
      score: p?.score as number | undefined,
      comment: String(p?.feedback || ""),
      advantages: "",
      disadvantages: "",
      suggestions: "",
    },
  ];
}

function collectFromPrimarySummary(result: Record<string, unknown>): {
  strengths: string[];
  weaknesses: string[];
  suggestions: string[];
} {
  const strengths: string[] = [];
  const weaknesses: string[] = [];
  const suggestions: string[] = [];
  const primary = (result.primary_indicator_summary as Array<Record<string, unknown>>) || [];

  for (const item of primary) {
    const name = canonicalPrimaryFeedbackName(String(item.primary_indicator_name || ""));
    if (!(PRIMARY_FEEDBACK_NAMES as readonly string[]).includes(name)) continue;

    const adv = pickPrimaryFieldText(String(item.advantages || ""));
    const dis = pickPrimaryFieldText(String(item.disadvantages || ""));
    const sug = pickPrimaryFieldText(String(item.improvement_suggestions || ""));
    const summary = pickPrimaryFieldText(String(item.summary_comment || ""));

    if (adv) strengths.push(withPrimaryPrefix(name, adv));
    if (dis) weaknesses.push(withPrimaryPrefix(name, dis));
    if (sug) suggestions.push(withPrimaryPrefix(name, sug));

    if (!summary) continue;

    const score = Number(item.mean);
    const line = withPrimaryPrefix(name, summary);
    if (Number.isNaN(score)) {
      if (!adv && !dis && !sug) strengths.push(line);
      continue;
    }
    if (score >= 3.5 && !adv) strengths.push(line);
    else if (score <= 2.8 && !dis) weaknesses.push(line);
    else if (!sug && score < 3.5) suggestions.push(line);
  }
  return { strengths, weaknesses, suggestions };
}

function buildComprehensiveComment(result: Record<string, unknown>): string {
  const final = String(result.final_comment || result.final_feedback || "").trim();
  if (final && !isBoilerplateFeedback(final) && !containsSecondaryDimensionText(final)) {
    return final;
  }

  const parts: string[] = [];
  const primary = (result.primary_indicator_summary as Array<Record<string, unknown>>) || [];
  for (const item of primary) {
    const name = canonicalPrimaryFeedbackName(String(item.primary_indicator_name || ""));
    if (!(PRIMARY_FEEDBACK_NAMES as readonly string[]).includes(name)) continue;
    const comment = pickPrimaryFieldText(String(item.summary_comment || ""));
    if (comment) {
      parts.push(`【${name}】\n${comment}`);
    }
  }
  return parts.join("\n\n");
}

export type PblFeedbackDisplay =
  | { mode: "sections"; strengths: string[]; weaknesses: string[]; suggestions: string[] }
  | { mode: "comprehensive"; text: string };

export function resolvePblFeedbackDisplay(
  result: Record<string, unknown>,
  _primaryCards: ReturnType<typeof buildPrimaryCards>
): PblFeedbackDisplay {
  const fromPrimary = collectFromPrimarySummary(result);

  const fromTopRaw = {
    strengths: filterPrimaryFeedbackLines(asStringList(result.strengths)),
    weaknesses: filterPrimaryFeedbackLines(asStringList(result.weaknesses)),
    suggestions: filterPrimaryFeedbackLines(
      asStringList(result.revision_suggestions ?? result.suggestions)
    ),
  };

  // primary_indicator_summary 优先；顶层 strengths 等仅作补全，再按一级指标去重
  const strengths = uniqueMeaningful([...fromPrimary.strengths, ...fromTopRaw.strengths]);
  const weaknesses = uniqueMeaningful([...fromPrimary.weaknesses, ...fromTopRaw.weaknesses]);
  const suggestions = uniqueMeaningful([...fromPrimary.suggestions, ...fromTopRaw.suggestions]);

  if (strengths.length + weaknesses.length + suggestions.length > 0) {
    return { mode: "sections", strengths, weaknesses, suggestions };
  }

  const comprehensive = buildComprehensiveComment(result);
  if (comprehensive) {
    return { mode: "comprehensive", text: comprehensive };
  }

  return { mode: "comprehensive", text: "暂无有效文字反馈。" };
}
