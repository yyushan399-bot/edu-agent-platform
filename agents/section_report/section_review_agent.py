"""
section_review_agent.py
项目化学习研究报告 —— 按章节审核智能体（修改版）

修改说明：
- 增加 run_review_loop() 实现评分→审核→重评的循环
- 审核通过后计算并输出章节总分、优点、缺点、改进建议
- 依赖 section_scoring_agent 中的评分函数
"""

import json
import math
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Callable, Tuple
from pathlib import Path

from pydantic import BaseModel, Field

from agents.group_project.pbl_config import DEFAULT_MODEL, DEFAULT_SCORING_TIMES
from agents.group_project.scoring_models import DeepSeekClient
from agents.section_report.section_config import (
    DEFAULT_CV_THRESHOLD,
    DEFAULT_MAX_REVIEW_ROUNDS,
    REFERENCE_LEAK_MARKERS,
    SECTION_NAMES,
)
from agents.section_report.section_scoring_agent import (
    CriterionSummary,
    rescore_criteria,
    score_criteria,
)
from services.section_graphrag_service import GraphRAGRetriever, create_section_retriever


# ============================================================
# 2. 数据结构
# ============================================================

class CriterionAuditResult(BaseModel):
    """单个指标的审核结果"""
    criterion_name: str
    passed: bool
    need_rescore: bool
    failed_checks: List[str] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    audit_comment: str = ""


class SectionAuditReport(BaseModel):
    """单个章节的完整审核报告"""
    section_name: str
    student_text: str = ""
    criterion_audits: List[CriterionAuditResult]
    overall_passed: bool
    need_rescore: bool
    failed_criteria: List[str] = Field(default_factory=list)
    audit_comment: str = ""
    rescore_feedback: Dict[str, Any] = Field(default_factory=dict)  # 供评分智能体重评用


# 最终输出结构（审核通过后）
class FinalSectionReport(BaseModel):
    """最终输出：章节总分 + 优点 + 缺点 + 改进建议"""
    section_name: str
    total_score: float               # 加权总分，满分5分
    strengths: List[str]             # 优点（平均分≥4.0的指标）
    weaknesses: List[str]            # 缺点（平均分≤2.5的指标）
    suggestions: List[str]           # 改进建议（从评分中收集）
    audit_rounds_used: int           # 实际使用的审核轮次


# ============================================================
# 3. 通用工具函数（与之前相同）
# ============================================================

def _to_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_plain(v) for v in value]
    return value


def _ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _coerce_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        if isinstance(value, float) and math.isnan(value):
            return default
        return float(value)
    except Exception:
        return default


def _normalize_text(text: str) -> str:
    text = str(text or "").lower()
    text = re.sub(r"\s+", "", text)
    punctuations = (
        r"，。！？、；：,.!?;:'"
        r'"“”‘’'
        r'（）()\[\]【】{}<>《》'
        r'\\\-_=+\*/\\|`~#￥$%^&·…'
    )
    text = re.sub(punctuations, "", text)
    return text


def _best_fuzzy_ratio(needle: str, haystack: str, *, max_windows: int = 240) -> float:
    n = _normalize_text(needle)
    h = _normalize_text(haystack)
    if not n:
        return 0.0
    if len(n) < 4:          # ← 从 8 改为 4
        return 0.0
    if n in h:
        return 1.0
    if len(h) <= len(n) * 3:
        return SequenceMatcher(None, n, h).ratio()
    window = min(max(len(n) * 2, 80), 500)
    step = max(window // 3, 40)
    starts = list(range(0, max(1, len(h) - window + 1), step))
    if len(starts) > max_windows:
        stride = max(1, len(starts) // max_windows)
        starts = starts[::stride][:max_windows]
    best = 0.0
    for start in starts:
        segment = h[start:start + window]
        ratio = SequenceMatcher(None, n, segment).ratio()
        if ratio > best:
            best = ratio
            if best >= 0.92:
                break
    return best

# ============================================================
# 4. 程序化审核：稳定性 + 证据可追溯性
# ============================================================

def check_score_stability(
    criterion_name: str,
    scores: List[Dict[str, Any]],
    cv_threshold: float = DEFAULT_CV_THRESHOLD,
) -> Dict[str, Any]:
    numeric_scores = [s.get("score", 0) for s in scores if isinstance(s.get("score"), (int, float))]
    if len(numeric_scores) < 2:
        return {
            "check_name": "多次评分稳定性检查",
            "passed": False,
            "issues": [f"{criterion_name} 评分次数不足，无法计算稳定性。"],
            "details": {"count": len(numeric_scores)},
        }
    mean = sum(numeric_scores) / len(numeric_scores)
    std = math.sqrt(sum((x - mean) ** 2 for x in numeric_scores) / len(numeric_scores))
    cv = std / mean if mean > 1e-8 else None
    if cv is None:
        return {
            "check_name": "多次评分稳定性检查",
            "passed": False,
            "issues": [f"{criterion_name} 无法计算 CV。"],
            "details": {"mean": mean, "std": std},
        }
    if cv <= cv_threshold:   # ← 改成 <=，CV 恰好等于阈值也算通过
        return {
            "check_name": "多次评分稳定性检查",
            "passed": True,
            "issues": [],
            "details": {"cv": round(cv, 3), "threshold": cv_threshold, "mean": round(mean, 2), "std": round(std, 2)},
        }
    return {
        "check_name": "多次评分稳定性检查",
        "passed": False,
        "issues": [f"{criterion_name} CV={cv:.3f}，超过 {cv_threshold:.2f}，评分不稳定，建议人工复核。"],
        "details": {"cv": round(cv, 3), "threshold": cv_threshold, "mean": round(mean, 2), "std": round(std, 2)},
    }



def check_evidence_traceability(
    criterion_name: str,
    scores: List[Dict[str, Any]],
    student_text: str,
) -> Dict[str, Any]:
    """
    证据可追溯性检查（弱化版）：
    - 硬性拦截：参考报告内容泄露（REFERENCE_LEAK_MARKERS）
    - 软性提示：文本匹配度极低时给 warning，但不硬性拦截
    - evidence 真实性最终由 LLM 语义审核判断
    """
    issues = []
    warnings = []
    details = {"evidence_checks": []}
    all_evidence = []
    for score_item in scores:
        evidence_list = _ensure_list(score_item.get("evidence", []))
        all_evidence.extend(evidence_list)
    if not all_evidence:
        return {
            "check_name": "证据可追溯性检查",
            "passed": False,
            "issues": [f"{criterion_name} 未提供任何 evidence，无法验证。"],
            "warnings": [],
            "details": details,
        }

    for idx, ev in enumerate(all_evidence, 1):
        ev_str = str(ev)

        # 1. 参考泄露检查 —— 硬性拦截
        for marker in REFERENCE_LEAK_MARKERS:
            if marker.lower() in ev_str.lower():
                issues.append(f"{criterion_name} evidence 中出现「{marker}」，疑似混入参考报告内容。")

        # 2. 文本匹配 —— 仅记录+warning，不硬性拦截（交给 LLM 自验证）
        ratio = _best_fuzzy_ratio(ev_str, student_text)
        details["evidence_checks"].append({
            "index": idx,
            "evidence_preview": ev_str[:120],
            "match_ratio": round(ratio, 3),
        })
        if ratio < 0.40:
            warnings.append(
                f"{criterion_name} 第 {idx} 条 evidence 字面匹配度仅 {ratio:.2f}，"
                f"建议语义审核重点核查其真实性。"
            )

    return {
        "check_name": "证据可追溯性检查",
        "passed": len(issues) == 0,   # 只有参考泄露才导致程序化不通过
        "issues": issues,
        "warnings": warnings,
        "details": details,
    }



# ============================================================
# 5. LLM 语义审核（保持不变）
# ============================================================

def build_semantic_audit_prompt(
    section_name: str,
    criterion_name: str,
    weight: float,
    rubrics: Dict[int, str],
    scores: List[Dict[str, Any]],
    mean: float,
    std: float,
    programmatic_checks: List[Dict[str, Any]],
    student_text: str,   # 新增参数
) -> Tuple[str, str]:
    """构建语义审核 Prompt，加入 evidence 真实性自验证"""

    # 量规描述
    rubric_lines = []
    for score in sorted(rubrics.keys(), reverse=True):
        rubric_lines.append(f"{score}分：{rubrics[score]}")

    # 评分摘要
    score_summaries = []
    for i, s in enumerate(scores[:5], 1):
        score_summaries.append(f"第{i}次：score={s.get('score')}, reason={str(s.get('reason', ''))[:100]}...")

    # 收集所有 evidence 用于 LLM 核查
    all_evidence = []
    for s in scores:
        all_evidence.extend(_ensure_list(s.get("evidence", [])))
    evidence_lines = []
    for idx, ev in enumerate(all_evidence, 1):
        evidence_lines.append(f"{idx}. {str(ev)[:250]}")
    evidence_block = "\n".join(evidence_lines) if evidence_lines else "（无 evidence）"

    system_prompt = f"""你是一名独立、严格的教育评价审核专家。

当前任务：审核【{section_name}】章节中【{criterion_name}】指标的评分结果。

审核目标：
1. 量规一致性：score 是否能被当前指标的量规描述支持？是否出现"理由像4分但给2分"的不一致？
2. 分数-理由一致性：score、reason、weakness、suggestion 是否自洽？
3. evidence 真实性（重点）：评分中列出的每一条 evidence 必须真实存在于学生文本中。如果 evidence 引用了学生文本里根本没有的句子、数据或概念，或明显是模型编造的，必须判不通过。
4. 汇总评价：mean={mean:.2f} 是否与 10 次评分的整体趋势一致？

你必须保守判断：
- 发现实质性疑点 → 判不通过并要求重评
- 只是措辞可改进 → 通过并给出 warning
- 输出必须是 JSON，不要 Markdown
""".strip()

    user_prompt = f"""## 审核指标：{criterion_name}（权重 {weight}）

### 量规描述（1-5分）
{"\n".join(rubric_lines)}

### 评分结果摘要（10次中的前5次）
{"\n".join(score_summaries)}

### 评分中的 Evidence 列表（请逐条核对其真实性）
{evidence_block}

### 学生实际文本（用于验证 evidence 真实性）
{student_text[:2000]}

### 统计结果
- 平均分：{mean:.2f}
- 标准差：{std:.2f}
- 一致性：{"稳定" if std < 0.5 else "需关注"}

### 程序化审核结果
{"\n".join([f"- {c['check_name']}：{'通过' if c['passed'] else '未通过'}" for c in programmatic_checks])}
{"\n".join([f"- 警告：{w}" for c in programmatic_checks for w in c.get('warnings', [])])}

### 请输出 JSON
{{
  "rubric_consistency": {{
    "passed": true,
    "issues": [],
    "warnings": []
  }},
  "score_reason_consistency": {{
    "passed": true,
    "issues": [],
    "warnings": []
  }},
  "evidence_authenticity": {{
    "passed": true,
    "issues": [],
    "warnings": []
  }},
  "overall_passed": true,
  "need_rescore": false,
  "audit_comment": "用中文简要说明审核结论，特别是 evidence 真实性方面的判断。"
}}
""".strip()
    return system_prompt, user_prompt



def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "是", "通过"}
    return default


def _normalize_semantic_audit(raw: Dict[str, Any]) -> Dict[str, Any]:
    """解析并标准化 LLM 返回的语义审核结果，新增 evidence_authenticity"""
    normalized = {}
    for key in ["rubric_consistency", "score_reason_consistency", "evidence_authenticity"]:
        item = raw.get(key, {})
        if not isinstance(item, dict):
            item = {}
        normalized[key] = {
            "passed": _safe_bool(item.get("passed"), default=False),
            "issues": [str(x) for x in _ensure_list(item.get("issues", [])) if str(x).strip()],
            "warnings": [str(x) for x in _ensure_list(item.get("warnings", [])) if str(x).strip()],
        }
    # overall_passed 默认取三个子项的合取
    normalized["overall_passed"] = _safe_bool(
        raw.get("overall_passed"),
        default=all(normalized[k]["passed"] for k in ["rubric_consistency", "score_reason_consistency", "evidence_authenticity"]),
    )
    normalized["need_rescore"] = _safe_bool(
        raw.get("need_rescore"),
        default=not normalized["overall_passed"],
    )
    normalized["audit_comment"] = str(raw.get("audit_comment", "")).strip()
    return normalized


# ============================================================
# 6. 单指标审核（整合程序化 + 语义）
# ============================================================

def audit_single_criterion(
    audit_llm: Any,
    section_name: str,
    criterion_name: str,
    weight: float,
    rubrics: Dict[int, str],
    scores: List[Dict[str, Any]],
    mean: float,
    std: float,
    student_text: str,
    cv_threshold: float = DEFAULT_CV_THRESHOLD,
) -> CriterionAuditResult:
    """单指标审核：程序化检查 + LLM 语义审核（含 evidence 自验证），带过程提示"""

    print(f"正在审核指标：{criterion_name}（权重 {weight}）...")

    # 程序化检查
    stability_check = check_score_stability(criterion_name, scores, cv_threshold)
    evidence_check = check_evidence_traceability(criterion_name, scores, student_text)
    programmatic_checks = [stability_check, evidence_check]
    programmatic_passed = all(c["passed"] for c in programmatic_checks)

    # 打印程序化检查结果
    for c in programmatic_checks:
        status = "✅" if c["passed"] else "❌"
        print(f"      {status} {c['check_name']}")
        for issue in c.get("issues", []):
            print(f"         ⚠️  {issue}")
        for warning in c.get("warnings", []):
            print(f"         ⚡ {warning}")

    # 语义审核（LLM 自验证 evidence 真实性）
    system_prompt, user_prompt = build_semantic_audit_prompt(
        section_name=section_name,
        criterion_name=criterion_name,
        weight=weight,
        rubrics=rubrics,
        scores=scores,
        mean=mean,
        std=std,
        programmatic_checks=programmatic_checks,
        student_text=student_text,
    )
    try:
        raw = audit_llm.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.0,
        )
        semantic_audit = _normalize_semantic_audit(raw)
    except Exception as exc:
        semantic_audit = {
            "rubric_consistency": {"passed": False, "issues": [f"语义审核模型调用失败：{exc}"], "warnings": []},
            "score_reason_consistency": {"passed": False, "issues": [f"语义审核模型调用失败：{exc}"], "warnings": []},
            "evidence_authenticity": {"passed": False, "issues": [f"语义审核模型调用失败，无法验证 evidence 真实性：{exc}"], "warnings": []},
            "overall_passed": False,
            "need_rescore": True,
            "audit_comment": f"语义审核失败：{exc}",
        }

    # 打印语义审核结果
    semantic_passed = semantic_audit.get("overall_passed", False)
    for key in ["rubric_consistency", "score_reason_consistency", "evidence_authenticity"]:
        group = semantic_audit.get(key, {})
        status = "✅" if group.get("passed", False) else "❌"
        print(f"      {status} {key}")
        for issue in group.get("issues", []):
            print(f"         ⚠️  {issue}")
        for warning in group.get("warnings", []):
            print(f"         ⚡ {warning}")

    passed = programmatic_passed and semantic_passed

    if passed:
        print(f"    ✅ 指标「{criterion_name}」审核通过")
    else:
        print(f"    ❌ 指标「{criterion_name}」审核未通过")

    if semantic_audit.get("audit_comment"):
        print(f"审核意见：{semantic_audit['audit_comment']}")

    # 收集失败项
    failed_checks = []
    for c in programmatic_checks:
        if not c["passed"]:
            failed_checks.append(c["check_name"])
    for key in ["rubric_consistency", "score_reason_consistency", "evidence_authenticity"]:
        if not semantic_audit.get(key, {}).get("passed", False):
            failed_checks.append(key)

    # 收集 issues 和 warnings
    issues = []
    warnings = []
    for c in programmatic_checks:
        issues.extend(c.get("issues", []))
        warnings.extend(c.get("warnings", []))
    for key in ["rubric_consistency", "score_reason_consistency", "evidence_authenticity"]:
        group = semantic_audit.get(key, {})
        issues.extend(group.get("issues", []))
        warnings.extend(group.get("warnings", []))

    return CriterionAuditResult(
        criterion_name=criterion_name,
        passed=passed,
        need_rescore=not passed,
        failed_checks=failed_checks,
        issues=issues,
        warnings=warnings,
        audit_comment=semantic_audit.get("audit_comment", ""),
    )
# ============================================================
# 7. 章节级审核（可审核全部或部分指标）
# ============================================================

def audit_section(
    audit_llm: Any,
    section_name: str,
    scoring_results: Dict[str, CriterionSummary],
    student_text: str,
    rubrics_from_graphrag: Dict[str, Dict[int, str]],
    cv_threshold: float = DEFAULT_CV_THRESHOLD,
    criteria_to_audit: Optional[List[str]] = None,
) -> SectionAuditReport:
    """
    对章节的部分或全部指标进行审核，带过程提示。
    scoring_results: {criterion_name: CriterionSummary}
    rubrics_from_graphrag: {criterion_name: {score: description}}
    """
    print(f"\n开始审核章节「{section_name}」，共 {len(scoring_results)} 个指标")
    if criteria_to_audit:
        print(f"   本次仅审核：{criteria_to_audit}")

    criterion_audits = []
    for crit_name, summary in scoring_results.items():
        if criteria_to_audit is not None and crit_name not in criteria_to_audit:
            continue
        rubrics = rubrics_from_graphrag.get(crit_name, {})
        scores_dicts = [s.model_dump() for s in summary.scores]
        audit = audit_single_criterion(
            audit_llm=audit_llm,
            section_name=section_name,
            criterion_name=crit_name,
            weight=summary.weight,
            rubrics=rubrics,
            scores=scores_dicts,
            mean=summary.mean,
            std=summary.std,
            student_text=student_text,
            cv_threshold=cv_threshold,
        )
        criterion_audits.append(audit)

    failed_criteria = [a.criterion_name for a in criterion_audits if not a.passed]
    overall_passed = len(failed_criteria) == 0

    # 章节级汇总打印
    print(f"\n{'─' * 50}")
    print(f"章节「{section_name}」审核汇总：")
    for audit in criterion_audits:
        status = "通过" if audit.passed else "未通过"
        print(f"   {status} │ {audit.criterion_name}")
        if not audit.passed and audit.failed_checks:
            print(f"         失败项：{', '.join(audit.failed_checks)}")
    print(f"{'─' * 50}")

    if overall_passed:
        print(f"章节「{section_name}」全部指标审核通过！")
    else:
        print(f"章节「{section_name}」审核未通过，需重评指标：{', '.join(failed_criteria)}")
    print(f"")

    # 构建 rescore_feedback
    rescore_feedback = {}
    for audit in criterion_audits:
        if not audit.passed:
            feedback_text = f"审核不通过。失败项：{', '.join(audit.failed_checks)}。问题：{'; '.join(audit.issues[:3])}。审核意见：{audit.audit_comment}"
            rescore_feedback[audit.criterion_name] = feedback_text
    audit_comment = f"【{section_name}】章节审核{'通过' if overall_passed else '未通过'}。"
    if not overall_passed:
        audit_comment += f"需重评指标：{', '.join(failed_criteria)}"

    return SectionAuditReport(
        section_name=section_name,
        student_text=student_text[:200],
        criterion_audits=criterion_audits,
        overall_passed=overall_passed,
        need_rescore=not overall_passed,
        failed_criteria=failed_criteria,
        audit_comment=audit_comment,
        rescore_feedback=rescore_feedback,
    )

# ============================================================
# 8. 最终报告生成（从评分结果汇总）
# ============================================================

# ============================================================
# 替换：generate_final_report
# ============================================================

def generate_final_report(
    section_name: str,
    scoring_results: Dict[str, CriterionSummary],
    audit_rounds: int,
    audit_llm: Any,   # 新增：用于 LLM 总结优点缺点
) -> FinalSectionReport:
    """
    从评分结果中计算加权总分，由 LLM 自然总结优点和缺点，不再硬按分数阈值分类。
    """
    # 1. 计算加权总分
    total_weight = 0.0
    weighted_sum = 0.0
    for summary in scoring_results.values():
        w = summary.weight
        total_weight += w
        weighted_sum += summary.mean * w
    total_score = weighted_sum / total_weight if total_weight > 0 else 0.0
    total_score = round(total_score, 2)

    # 2. 收集改进建议（保留原逻辑，去掉指标名前缀）
    suggestions = []
    for summary in scoring_results.values():
        if summary.scores and summary.scores[0].suggestion:
            sg = str(summary.scores[0].suggestion).strip()
            for prefix in [f"【{summary.criterion_name}】", summary.criterion_name]:
                if sg.startswith(prefix):
                    sg = sg[len(prefix):].strip("：:").strip()
            if sg:
                suggestions.append(sg)

    # 3. 构建指标数据摘要，供 LLM 总结优点和缺点
    criteria_summaries = []
    for crit_name, summary in scoring_results.items():
        reasons = []
        for s in summary.scores:
            if s.reason:
                reasons.append(s.reason)
        unique_reasons = list(dict.fromkeys(reasons))[:3]
        weakness = summary.scores[0].weakness if summary.scores else "无"
        suggestion = summary.scores[0].suggestion if summary.scores else "无"

        criteria_summaries.append(
            f"指标：{crit_name}（权重{summary.weight}，平均分{summary.mean:.2f}）\n"
            f"  综合评语：{summary.summary_reason}\n"
            f"  主要理由：{'；'.join(unique_reasons)}\n"
            f"  不足：{weakness}\n"
            f"  建议：{suggestion}"
        )

    criteria_block = "\n\n".join(criteria_summaries)

    def _threshold_strengths_weaknesses() -> tuple[list[str], list[str]]:
        fallback_strengths: list[str] = []
        fallback_weaknesses: list[str] = []
        for summary in scoring_results.values():
            reason = summary.summary_reason.strip()
            for prefix in [f"【{summary.criterion_name}】", summary.criterion_name]:
                if reason.startswith(prefix):
                    reason = reason[len(prefix):].strip("：:").strip()
            if summary.mean >= 4.0 and reason:
                fallback_strengths.append(f"{reason}（{summary.mean:.2f}分）")
            elif summary.mean <= 2.5 and reason:
                fallback_weaknesses.append(f"{reason}（{summary.mean:.2f}分）")
        return fallback_strengths, fallback_weaknesses

    # 4. 调用 LLM 自然总结优点和缺点
    system_prompt = f"""你是一名资深教育评价专家，擅长对项目化学习研究报告撰写综合性评语。

请根据以下各指标的评分结果，自然、流畅地总结该章节报告的优点和缺点。

要求：
1. 不要按分数硬性分类（如"≥4.0为优点"），而是根据评语内容自然归纳
2. 优点：报告做得好的方面，用鼓励性、具体化的语言，2-3条即可
3. 缺点：报告需要改进的方面，用建设性、具体化的语言，2-3条即可
4. 每条优点/缺点要具体、有针对性，引用报告中的具体表现
5. 不要出现"该指标"等机械表达，直接评价报告本身
6. 输出必须是 JSON，不要 Markdown

输出格式：
{{
  "strengths": ["优点1...", "优点2..."],
  "weaknesses": ["缺点1...", "缺点2..."]
}}
""".strip()

    user_prompt = f"""## 章节：{section_name}
## 章节总分：{total_score}/5.0

## 各指标评分详情
{criteria_block}

## 任务
请根据以上评分结果，自然总结该章节报告的优点和缺点。
""".strip()

    try:
        raw = audit_llm.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
        )
        strengths = _ensure_list(raw.get("strengths", []))
        weaknesses = _ensure_list(raw.get("weaknesses", []))
    except Exception as exc:
        print(f" LLM 总结优点缺点失败：{exc}，使用备用阈值方案")
        strengths, weaknesses = _threshold_strengths_weaknesses()

    if not strengths and not weaknesses:
        strengths, weaknesses = _threshold_strengths_weaknesses()

    return FinalSectionReport(
        section_name=section_name,
        total_score=total_score,
        strengths=strengths,
        weaknesses=weaknesses,
        suggestions=suggestions,
        audit_rounds_used=audit_rounds,
    )


# ============================================================
# 9. 核心循环：评分 → 审核 → 重评（直到通过或达到最大轮次）
# ============================================================

def run_review_loop(
    section_name: str,
    student_text: str,
    scoring_llm: DeepSeekClient,
    audit_llm: DeepSeekClient,
    retriever: GraphRAGRetriever,
    max_rounds: int = 3,
    scoring_times: int = DEFAULT_SCORING_TIMES,
    cv_threshold: float = DEFAULT_CV_THRESHOLD,
) -> FinalSectionReport:
    """
    执行完整的评分-审核循环，带详细过程提示，返回最终报告。
    
    修改要点：
    - 第1轮审核全部指标
    - 后续轮次只审核上一轮未通过的指标（已通过的不再重复审核）
    - 重评也只针对未通过的指标
    """
    context = retriever.retrieve_full_context(section_name)
    rubrics_map = {}
    for crit in context["criteria"]:
        rubrics_map[crit["criterion_name"]] = crit["rubrics"]

    print(f"\n{'='*60}")
    print(f"开始对章节「{section_name}」进行评分与审核循环")
    print(f"   最大审核轮次：{max_rounds}  │  每指标评分次数：{scoring_times}")
    print(f"{'='*60}")

    print(f"\n第 1 步：首次评分（所有指标）")
    current_results = score_criteria(
        llm=scoring_llm,
        retriever=retriever,
        section_name=section_name,
        student_text=student_text,
        criteria_names=None,
        scoring_times=scoring_times,
    )

    # 记录上一轮未通过的指标，初始为 None 表示第1轮需审核全部
    failed_criteria: Optional[List[str]] = None

    for round_num in range(1, max_rounds + 1):
        print(f"\n{'='*60}")
        print(f"审核轮次 {round_num} / {max_rounds}")
        print(f"{'='*60}")

        # 第1轮审核全部，后续轮次只审核上一轮未通过的指标
        if round_num == 1:
            criteria_to_audit = None
            print("本轮审核：全部指标")
        else:
            criteria_to_audit = failed_criteria
            print(f"本轮仅审核上轮未通过的指标：{failed_criteria}")

        audit_report = audit_section(
            audit_llm=audit_llm,
            section_name=section_name,
            scoring_results=current_results,
            student_text=student_text,
            rubrics_from_graphrag=rubrics_map,
            cv_threshold=cv_threshold,
            criteria_to_audit=criteria_to_audit,
        )

        if audit_report.overall_passed:
            print(f"\n第 {round_num} 轮审核全部通过！")
            return generate_final_report(section_name, current_results, round_num, audit_llm)

        if round_num == max_rounds:
            print(f"\n已达到最大轮次 {max_rounds}，审核未完全通过，输出最终报告。")
            return generate_final_report(section_name, current_results, round_num, audit_llm)

        # 保存本轮未通过的指标，用于下一轮针对性审核
        failed_criteria = audit_report.failed_criteria
        feedback_map = audit_report.rescore_feedback

        print(f"\n🔄 进入重评阶段，以下指标将重新评分：")
        for crit_name in failed_criteria:
            feedback = feedback_map.get(crit_name, "")
            print(f"   • {crit_name}")
            print(f"     反馈：{feedback[:120]}...")

        current_results = rescore_criteria(
            llm=scoring_llm,
            retriever=retriever,
            section_name=section_name,
            student_text=student_text,
            previous_results=current_results,
            criteria_to_rescore=failed_criteria,
            feedback_map=feedback_map,
            scoring_times=scoring_times,
        )
        print(f"\n重评完成，进入下一轮审核...")

    # 理论上不会执行到这里，因为循环内已返回
    return generate_final_report(section_name, current_results, max_rounds, audit_llm)
# ============================================================
# 10. 命令行入口（用于独立运行审核循环）
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="项目化学习报告 — 章节审核循环")
    parser.add_argument("--section", required=True, choices=SECTION_NAMES)
    parser.add_argument("--text", required=True, help="学生章节文本")
    parser.add_argument("--text-file", default=None)
    parser.add_argument("--out", default="final_report.json", help="最终报告输出路径")
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--model", default="deepseek-v4-flash")
    args = parser.parse_args()

    if args.text_file:
        student_text = Path(args.text_file).read_text(encoding="utf-8")
    else:
        student_text = args.text

    scoring_llm = DeepSeekClient(model=args.model)
    audit_llm = DeepSeekClient(model=args.model)
    retriever = create_section_retriever()

    final_report = run_review_loop(
        section_name=args.section,
        student_text=student_text,
        scoring_llm=scoring_llm,
        audit_llm=audit_llm,
        retriever=retriever,
        max_rounds=args.max_rounds,
    )

    out_path = Path(args.out)
    out_path.write_text(json.dumps(final_report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n最终报告已保存至：{args.out}")
    print(f"章节总分：{final_report.total_score}")
    print(f"优点：{final_report.strengths}")
    print(f"缺点：{final_report.weaknesses}")
    print(f"改进建议：{final_report.suggestions}")

    retriever.close()


if __name__ == "__main__":
    main()