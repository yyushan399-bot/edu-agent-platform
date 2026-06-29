from __future__ import annotations

import json
import math
import re
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Optional, Tuple


DIMENSION_NAMES = {
    "problem_posing": "问题提出",
    "plan_novelty": "方案新颖性",
    "innovation_representation": "创新表征",
    "innovation_expression": "创新表达",
}

DEFAULT_CV_THRESHOLD = 0.20

REFERENCE_LEAK_MARKERS = [
    "GraphRAG",
    "graphrag",
    "参考报告",
    "参考片段",
    "优质报告",
    "普通报告",
    "样例报告",
    "对照样例",
    "检索片段",
]


# ============================================================
# 通用工具
# ============================================================

def _to_plain(value: Any) -> Any:
    """兼容 Pydantic model、普通 dict/list 和基础类型。"""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_plain(v) for v in value]
    return value


def _json_dumps(value: Any, *, max_chars: Optional[int] = None) -> str:
    text = json.dumps(_to_plain(value), ensure_ascii=False, indent=2)
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars] + "\n...[已截断]..."
    return text


def _truncate(text: str, max_chars: int) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[已截断]..."


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
    """
    用于证据查验的弱规范化：
    - 去掉空白、常见标点和 Markdown 标记
    - 转小写
    """
    text = str(text or "").lower()
    text = re.sub(r"\s+", "", text)
    text = re.sub(
        r"[，。！？、；：,.!?;:'\"“”‘’（）()\[\]【】{}<>《》\-_=+*/\\|`~#￥$%^&·…]",
        "",
        text,
    )
    return text


def _extract_original_blocks_from_student_dimension_text(student_dimension_text: str) -> List[str]:
    """
    从 student_dimension_text 中抽取“原文”部分。
    格式：
        【学生报告xxx相关片段 1】
        片段ID：...
        相关性分数：...
        原文：
        ...
    """
    text = student_dimension_text or ""
    blocks: List[str] = []

    pattern = re.compile(
        r"原文：\s*(.*?)(?=\n\s*【学生报告.*?相关片段\s*\d+】|\Z)",
        re.S,
    )
    for match in pattern.finditer(text):
        block = match.group(1).strip()
        if block:
            blocks.append(block)

    if blocks:
        return blocks

    # 如果格式不是上述形式，就整体作为一个待核验片段。
    return [text.strip()] if text.strip() else []


def _best_fuzzy_ratio(needle: str, haystack: str, *, max_windows: int = 240) -> float:
    """
    判断 needle 是否大致出现在 haystack 中。
    证据常会被模型轻微改写，不能只做 exact match。
    使用分段窗口 + SequenceMatcher，避免对超长报告做全量 O(n*m) 比较。
    """
    n = _normalize_text(needle)
    h = _normalize_text(haystack)

    if not n:
        return 0.0

    if n in h:
        return 1.0

    # 太短的证据不适合模糊匹配，容易误判。
    if len(n) < 8:
        return 0.0

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


def _dimension_result_scores(dimension_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    scores = _ensure_list(dimension_result.get("scores", []))
    clean_scores: List[Dict[str, Any]] = []
    for item in scores:
        item = _to_plain(item)
        if isinstance(item, dict):
            clean_scores.append(item)
    return clean_scores


# ============================================================
# 程序化审核：稳定性 + 证据可追溯性
# ============================================================

def check_score_stability(
    dimension_key: str,
    dimension_result: Dict[str, Any],
    cv_threshold: float = DEFAULT_CV_THRESHOLD,
) -> Dict[str, Any]:
    dimension_name = dimension_result.get("dimension_name") or DIMENSION_NAMES.get(dimension_key, dimension_key)
    cv = _coerce_float(dimension_result.get("cv"))

    if cv is None:
        return {
            "check_name": "多次评分稳定性检查",
            "passed": False,
            "issues": [f"{dimension_name} 维度缺少 CV，无法确认多次评分稳定性。"],
            "details": {"cv": None, "threshold": cv_threshold},
        }

    if cv < cv_threshold:
        return {
            "check_name": "多次评分稳定性检查",
            "passed": True,
            "issues": [],
            "details": {"cv": cv, "threshold": cv_threshold},
        }

    return {
        "check_name": "多次评分稳定性检查",
        "passed": False,
        "issues": [f"{dimension_name} 维度 CV={cv:.3f}，达到或超过 {cv_threshold:.2f}，不允许直接输出，必须重新评分。"],
        "details": {"cv": cv, "threshold": cv_threshold},
    }


def check_student_text_traceability(
    dimension_key: str,
    dimension_result: Dict[str, Any],
    merged_report_context: str,
) -> Dict[str, Any]:
    """
    学生报告真实性核查。
    检查 student_dimension_text 是否确实来自当前学生报告正文（纯文本）。
    """
    dimension_name = dimension_result.get("dimension_name") or DIMENSION_NAMES.get(dimension_key, dimension_key)
    student_dimension_text = str(dimension_result.get("student_dimension_text") or "")

    issues: List[str] = []
    details: Dict[str, Any] = {
        "student_dimension_text_present": bool(student_dimension_text.strip()),
        "student_text_block_matches": [],
    }

    if not merged_report_context or not str(merged_report_context).strip():
        issues.append(
            f"{dimension_name} 维度无法核查 student_dimension_text，因为 merged_report_context 为空。"
        )

    if not student_dimension_text.strip():
        issues.append(
            f"{dimension_name} 维度缺少 student_dimension_text，无法核查学生报告相关片段是否来自原文。"
        )
    else:
        for marker in REFERENCE_LEAK_MARKERS:
            if marker.lower() in student_dimension_text.lower():
                issues.append(
                    f"{dimension_name} 维度 student_dimension_text 中出现“{marker}”，疑似混入 GraphRAG/参考报告内容。"
                )

        original_blocks = _extract_original_blocks_from_student_dimension_text(student_dimension_text)

        if not original_blocks:
            issues.append(
                f"{dimension_name} 维度 student_dimension_text 无法抽取出可核查的学生报告片段。"
            )

        for idx, block in enumerate(original_blocks, start=1):
            # 纯文本版：直接进行模糊匹配，无 OCR 跳过逻辑
            ratio = _best_fuzzy_ratio(block, merged_report_context)
            matched = ratio >= 0.7

            details["student_text_block_matches"].append(
                {
                    "block_index": idx,
                    "matched": matched,
                    "match_ratio": round(ratio, 3),
                    "preview": block[:160],
                }
            )

            if not matched:
                issues.append(
                    f"{dimension_name} 维度 student_dimension_text 第 {idx} 个原文片段无法在学生报告中稳定匹配，疑似不是当前学生报告原文。"
                )

    return {
        "check_name": "学生报告真实性检查",
        "passed": len(issues) == 0,
        "issues": issues,
        "details": details,
    }


# ============================================================
# LLM 语义审核：量规一致性 + 分数理由一致性
# ============================================================

def build_semantic_audit_prompt(
    *,
    dimension_key: str,
    dimension_result: Dict[str, Any],
    rubric: str,
    merged_report_context: str,
    programmatic_checks: List[Dict[str, Any]],
) -> Tuple[str, str]:
    """
    构建语义审核 prompt。
    只检查：
    1. 量规一致性；
    2. 分数—理由一致性。
    """
    dimension_name = dimension_result.get("dimension_name") or DIMENSION_NAMES.get(dimension_key, dimension_key)

    compact_result = {
        "dimension_key": dimension_key,
        "dimension_name": dimension_name,
        "student_dimension_text": dimension_result.get("student_dimension_text", ""),
        "scores": _dimension_result_scores(dimension_result),
        "mean": dimension_result.get("mean"),
        "std": dimension_result.get("std"),
        "cv": dimension_result.get("cv"),
        "min_score": dimension_result.get("min_score"),
        "max_score": dimension_result.get("max_score"),
        "consistency_level": dimension_result.get("consistency_level"),
        "summary_comment": dimension_result.get("summary_comment"),
    }

    system_prompt = f"""
你是一个独立、严格、保守的教育评价审核智能体。
你只审核 creativity_agent 已经给出的【{dimension_name}】维度评分结果，不重新评分，不替学生补充内容。

你的审核目标只有两项语义检查：

1. 量规一致性检查：
   - 是否只评价当前维度【{dimension_name}】，没有混入其他维度的评价标准。
   - 给出的 score 是否能被当前维度量规描述支持。
   - 是否出现“理由像 4 分，但分数给 2 分”或“理由像 2 分，但分数给 4 分”的不一致。

2. 分数—理由一致性检查：
   - score、reason、weakness、suggestion 是否自洽。
   - 是否出现分数很高但 weakness 非常严重，或分数很低但 reason 主要在夸优点。
   - suggestion 是否对应 weakness。
   - summary_comment 是否与多次评分均值大体一致。
   - 是否暗示或输出总分。

你必须保守判断：
- 只要发现实质性疑点，就判该项不通过并要求重评。
- 如果只是措辞可改进但不影响评分可靠性，可以通过并给出 warning。
- 输出必须是 JSON object，不要输出 Markdown。
""".strip()

    user_prompt = f"""
# 当前审核维度
dimension_key: {dimension_key}
dimension_name: {dimension_name}

# 当前维度量规
{rubric}

# creativity_agent 对该维度的评分结果
{_json_dumps(compact_result, max_chars=45000)}

# 程序化检查结果
{_json_dumps(programmatic_checks, max_chars=12000)}

# 请严格输出以下 JSON 格式

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
  "overall_passed": true,
  "need_rescore": false,
  "audit_comment": "用中文简要说明审核结论。"
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
    """
    规范化语义审核结果。
    """
    normalized: Dict[str, Any] = {}
    for key in ["rubric_consistency", "score_reason_consistency"]:
        item = raw.get(key, {})
        if not isinstance(item, dict):
            item = {}
        normalized[key] = {
            "passed": _safe_bool(item.get("passed"), default=False),
            "issues": [str(x) for x in _ensure_list(item.get("issues", [])) if str(x).strip()],
            "warnings": [str(x) for x in _ensure_list(item.get("warnings", [])) if str(x).strip()],
        }

    normalized["overall_passed"] = _safe_bool(
        raw.get("overall_passed"),
        default=all(normalized[k]["passed"] for k in [
            "rubric_consistency",
            "score_reason_consistency",
        ]),
    )
    normalized["need_rescore"] = _safe_bool(
        raw.get("need_rescore"),
        default=not normalized["overall_passed"],
    )
    normalized["audit_comment"] = str(raw.get("audit_comment", "")).strip()

    return normalized


# ============================================================
# 最终输出
# ============================================================

def build_dimension_summary(dimension_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    summary: List[Dict[str, Any]] = []

    for dimension_key, raw_result in dimension_results.items():
        result = _to_plain(raw_result)
        if not isinstance(result, dict):
            continue

        summary.append(
            {
                "dimension_key": dimension_key,
                "dimension_name": result.get("dimension_name") or DIMENSION_NAMES.get(dimension_key, dimension_key),
                "mean": result.get("mean"),
                "std": result.get("std"),
                "cv": result.get("cv"),
                "min_score": result.get("min_score"),
                "max_score": result.get("max_score"),
                "consistency_level": result.get("consistency_level"),
                "summary_comment": result.get("summary_comment", ""),
            }
        )

    # 按预设维度顺序稳定输出。
    order = {key: idx for idx, key in enumerate(DIMENSION_NAMES)}
    summary.sort(key=lambda item: order.get(item["dimension_key"], 999))
    return summary


def build_overall_explanation(
    *,
    audit_passed: bool,
    dimension_summary: List[Dict[str, Any]],
    audit_records: List[Dict[str, Any]],
    max_review_rounds_reached: bool = False,
) -> str:
    if audit_passed:
        lines = [
            "审核通过：四个维度均通过学生报告真实性、量规一致性、分数—理由一致性和多次评分稳定性检查。",
            "各维度平均分如下：",
        ]
    else:
        lines = [
            "审核未通过：仍有维度未通过至少一项审核检查。",
        ]
        if max_review_rounds_reached:
            lines.append("已达到自动重评轮数上限，系统不进入人工复核，而是保守输出当前各维度结果，并附带失败原因。")
        lines.append("当前各维度平均分如下，仅供复核参考：")

    for item in dimension_summary:
        cv_text = "无" if item.get("cv") is None else f"{float(item.get('cv')):.3f}"
        mean_value = item.get("mean")
        try:
            mean_text = f"{float(mean_value):.2f}"
        except Exception:
            mean_text = str(mean_value)

        lines.append(
            f"- {item.get('dimension_name')}：平均分 {mean_text}，CV={cv_text}，一致性={item.get('consistency_level')}"
        )

    # 给出最后一次审核的简要失败原因，便于定位。
    if not audit_passed and audit_records:
        last = audit_records[-1]
        failures = []
        for dimension_audit in last.get("dimension_audits", []):
            if not dimension_audit.get("passed", False):
                dimension_name = dimension_audit.get("dimension_name")
                issue_texts = []
                for check in dimension_audit.get("checks", []):
                    for issue in check.get("issues", []):
                        issue_texts.append(str(issue))
                semantic = dimension_audit.get("semantic_audit", {})
                for group_key in ["rubric_consistency", "score_reason_consistency"]:
                    for issue in semantic.get(group_key, {}).get("issues", []):
                        issue_texts.append(str(issue))
                failures.append(f"{dimension_name}：{'；'.join(issue_texts[:4])}")

        if failures:
            lines.append("最后一次审核未通过原因摘要：")
            lines.extend(f"- {x}" for x in failures)

    return "\n".join(lines)


# ============================================================
# 审核 Agent
# ============================================================

class IndependentAuditAgent:
    def __init__(
        self,
        audit_llm: Any,
        scoring_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
        max_review_rounds: Optional[int] = 2,
        cv_threshold: float = DEFAULT_CV_THRESHOLD,
    ) -> None:
        self.audit_llm = audit_llm
        self.scoring_fn = scoring_fn
        self.max_review_rounds = max_review_rounds
        self.cv_threshold = cv_threshold

    def _verbose_print(self, state: Dict[str, Any], message: str) -> None:
        if state.get("verbose", True):
            print(message, flush=True)

    def _print_check_result(
        self,
        state: Dict[str, Any],
        *,
        check_name: str,
        passed: bool,
        issues: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None,
    ) -> None:
        result_text = "通过" if passed else "未通过"
        self._verbose_print(state, f"[creativity_Review]   {check_name}：{result_text}")

        for issue in issues or []:
            issue_text = str(issue).strip()
            if issue_text:
                self._verbose_print(state, f"[creativity_Review]     问题：{issue_text}")

        for warning in warnings or []:
            warning_text = str(warning).strip()
            if warning_text:
                self._verbose_print(state, f"[creativity_Review]     提醒：{warning_text}")

    def _semantic_audit_dimension(
        self,
        *,
        dimension_key: str,
        dimension_result: Dict[str, Any],
        rubric: str,
        merged_report_context: str,
        programmatic_checks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        system_prompt, user_prompt = build_semantic_audit_prompt(
            dimension_key=dimension_key,
            dimension_result=dimension_result,
            rubric=rubric,
            merged_report_context=merged_report_context,
            programmatic_checks=programmatic_checks,
        )

        try:
            raw = self.audit_llm.chat_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.0,
            )
            return _normalize_semantic_audit(raw)

        except Exception as exc:
            # 审核模型失败时，保守判为不通过，避免放行未经审核结果。
            return {
                "rubric_consistency": {
                    "passed": False,
                    "issues": [f"语义审核模型调用失败，无法确认量规一致性：{exc}"],
                    "warnings": [],
                },
                "score_reason_consistency": {
                    "passed": False,
                    "issues": [f"语义审核模型调用失败，无法确认分数—理由一致性：{exc}"],
                    "warnings": [],
                },
                "overall_passed": False,
                "need_rescore": True,
                "audit_comment": f"语义审核失败：{exc}",
            }

    def audit_one_dimension(
        self,
        *,
        dimension_key: str,
        dimension_result: Dict[str, Any],
        rubric: str,
        merged_report_context: str,
        state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        state = state or {}

        dimension_result = _to_plain(dimension_result)
        if not isinstance(dimension_result, dict):
            dimension_result = {}

        dimension_name = dimension_result.get("dimension_name") or DIMENSION_NAMES.get(dimension_key, dimension_key)

        self._verbose_print(
            state,
            f"[creativity_Review] 开始审核维度：{dimension_name} ({dimension_key})",
        )

        self._verbose_print(state, "[creativity_Review]   正在审核：多次评分稳定性")
        stability_check = check_score_stability(
            dimension_key=dimension_key,
            dimension_result=dimension_result,
            cv_threshold=self.cv_threshold,
        )
        self._print_check_result(
            state,
            check_name="多次评分稳定性检查",
            passed=bool(stability_check.get("passed", False)),
            issues=[str(x) for x in stability_check.get("issues", [])],
        )

        self._verbose_print(state, "[creativity_Review]   正在审核：学生报告真实性 / student_dimension_text 可追溯性")
        student_text_check = check_student_text_traceability(
            dimension_key=dimension_key,
            dimension_result=dimension_result,
            merged_report_context=merged_report_context,
        )
        self._print_check_result(
            state,
            check_name="学生报告真实性检查",
            passed=bool(student_text_check.get("passed", False)),
            issues=[str(x) for x in student_text_check.get("issues", [])],
        )

        programmatic_checks = [stability_check, student_text_check]

        self._verbose_print(state, "[creativity_Review]   正在审核：量规一致性、分数—理由一致性")
        semantic_audit = self._semantic_audit_dimension(
            dimension_key=dimension_key,
            dimension_result=dimension_result,
            rubric=rubric,
            merged_report_context=merged_report_context,
            programmatic_checks=programmatic_checks,
        )

        semantic_groups = [
            ("rubric_consistency", "量规一致性检查"),
            ("score_reason_consistency", "分数—理由一致性检查"),
        ]

        for group_key, group_name in semantic_groups:
            group = semantic_audit.get(group_key, {})
            self._print_check_result(
                state,
                check_name=group_name,
                passed=bool(group.get("passed", False)),
                issues=[str(x) for x in group.get("issues", [])],
                warnings=[str(x) for x in group.get("warnings", [])],
            )

        audit_comment = str(semantic_audit.get("audit_comment", "")).strip()
        if audit_comment:
            self._verbose_print(state, f"[creativity_Review]   语义审核总结：{audit_comment}")

        programmatic_passed = all(check.get("passed", False) for check in programmatic_checks)
        semantic_passed = bool(semantic_audit.get("overall_passed", False))
        passed = programmatic_passed and semantic_passed

        failed_checks: List[str] = []
        for check in programmatic_checks:
            if not check.get("passed", False):
                failed_checks.append(check.get("check_name", "程序化检查"))

        for group_key, group_name in semantic_groups:
            if not semantic_audit.get(group_key, {}).get("passed", False):
                failed_checks.append(group_name)

        self._verbose_print(
            state,
            f"[creativity_Review] 维度审核结果：{dimension_name} {'通过' if passed else '未通过'}",
        )
        if failed_checks:
            self._verbose_print(state, f"[creativity_Review]   未通过项目：{failed_checks}")

        return {
            "dimension_key": dimension_key,
            "dimension_name": dimension_name,
            "passed": passed,
            "need_rescore": not passed,
            "failed_checks": failed_checks,
            "checks": programmatic_checks,
            "semantic_audit": semantic_audit,
        }

    def audit_all_dimensions(
        self,
        state: Dict[str, Any],
        dimension_keys: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        审核维度。

        - 第 0 轮通常审核全部维度。
        - 自动重评之后，只审核本轮刚重评的失败维度，避免已通过维度被重复审核后又被模型判为不通过。
        """
        merged_report_context = state.get("merged_report_context", "")
        dimension_results = _to_plain(state.get("dimension_results", {}))
        rubrics = _to_plain(state.get("rubrics", {}))

        if not isinstance(dimension_results, dict):
            dimension_results = {}
        if not isinstance(rubrics, dict):
            rubrics = {}

        dimension_audits: List[Dict[str, Any]] = []
        failed_dimension_keys: List[str] = []

        expected_keys = list(DIMENSION_NAMES.keys())
        all_keys = expected_keys + [k for k in dimension_results.keys() if k not in expected_keys]

        if dimension_keys is not None:
            requested_keys = [str(k) for k in dimension_keys]
            requested_set = set(requested_keys)
            all_keys = [k for k in all_keys if k in requested_set]
            all_keys.extend([k for k in requested_keys if k not in all_keys])

        self._verbose_print(state, "[creativity_Review] ============================================================")
        if dimension_keys is None:
            self._verbose_print(state, f"[creativity_Review] 待审核维度数量：{len(all_keys)}（全量审核）")
        else:
            self._verbose_print(state, f"[creativity_Review] 待审核维度数量：{len(all_keys)}（仅审核本轮重评维度：{all_keys}）")
        self._verbose_print(state, f"[creativity_Review] 学生报告上下文长度：{len(merged_report_context or '')}")
        self._verbose_print(state, "[creativity_Review] 学生报告真实性检查：已开启")
        self._verbose_print(state, "[creativity_Review] ============================================================")

        for dimension_key in all_keys:
            if dimension_key not in dimension_results:
                dimension_name = DIMENSION_NAMES.get(dimension_key, dimension_key)
                self._verbose_print(
                    state,
                    f"[creativity_Review] 开始审核维度：{dimension_name} ({dimension_key})",
                )
                self._verbose_print(state, "[creativity_Review]   结果完整性检查：未通过")
                self._verbose_print(state, f"[creativity_Review]     问题：缺少 {dimension_name} 维度评分结果。")

                audit = {
                    "dimension_key": dimension_key,
                    "dimension_name": dimension_name,
                    "passed": False,
                    "need_rescore": True,
                    "failed_checks": ["结果完整性检查"],
                    "checks": [
                        {
                            "check_name": "结果完整性检查",
                            "passed": False,
                            "issues": [f"缺少 {dimension_name} 维度评分结果。"],
                            "details": {},
                        }
                    ],
                    "semantic_audit": {
                        "overall_passed": False,
                        "need_rescore": True,
                        "audit_comment": "缺少该维度评分结果。",
                    },
                }
                dimension_audits.append(audit)
                failed_dimension_keys.append(dimension_key)
                self._verbose_print(state, "[creativity_Review] ------------------------------------------------------------")
                continue

            rubric = str(rubrics.get(dimension_key) or "")
            if not rubric:
                rubric = "[未提供当前维度量规]"

            audit = self.audit_one_dimension(
                dimension_key=dimension_key,
                dimension_result=dimension_results.get(dimension_key, {}),
                rubric=rubric,
                merged_report_context=merged_report_context,
                state=state,
            )
            dimension_audits.append(audit)
            if not audit.get("passed", False):
                failed_dimension_keys.append(dimension_key)

            self._verbose_print(state, "[creativity_Review] ------------------------------------------------------------")

        passed = len(failed_dimension_keys) == 0

        self._verbose_print(
            state,
            f"[creativity_Review] 本轮总体审核结果：{'通过' if passed else '未通过'}",
        )
        self._verbose_print(
            state,
            f"[creativity_Review] 本轮失败维度：{failed_dimension_keys if failed_dimension_keys else '无'}",
        )
        self._verbose_print(state, "[creativity_Review] ============================================================")

        return {
            "passed": passed,
            "failed_dimension_keys": failed_dimension_keys,
            "dimension_audits": dimension_audits,
            "audit_scope": "all" if dimension_keys is None else "failed_only",
            "audited_dimension_keys": all_keys,
        }

    def _build_rescore_feedback(self, audit_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        将本轮审核不通过原因整理成按维度索引的反馈，
        供评分智能体下一轮重评时使用。
        """
        feedback: Dict[str, Any] = {}

        for dimension_audit in audit_result.get("dimension_audits", []):
            if dimension_audit.get("passed", False):
                continue

            dimension_key = dimension_audit.get("dimension_key")
            if not dimension_key:
                continue

            issues: List[str] = []
            warnings: List[str] = []

            for check in dimension_audit.get("checks", []):
                check_name = check.get("check_name", "未知检查")
                for issue in check.get("issues", []):
                    issue_text = str(issue).strip()
                    if issue_text:
                        issues.append(f"{check_name}：{issue_text}")
                for warning in check.get("warnings", []):
                    warning_text = str(warning).strip()
                    if warning_text:
                        warnings.append(f"{check_name}：{warning_text}")

            semantic_audit = dimension_audit.get("semantic_audit", {})
            semantic_names = {
                "rubric_consistency": "量规一致性检查",
                "score_reason_consistency": "分数—理由一致性检查",
            }

            for group_key, group_name in semantic_names.items():
                group = semantic_audit.get(group_key, {})
                for issue in group.get("issues", []):
                    issue_text = str(issue).strip()
                    if issue_text:
                        issues.append(f"{group_name}：{issue_text}")
                for warning in group.get("warnings", []):
                    warning_text = str(warning).strip()
                    if warning_text:
                        warnings.append(f"{group_name}：{warning_text}")

            feedback[dimension_key] = {
                "dimension_key": dimension_key,
                "dimension_name": dimension_audit.get("dimension_name"),
                "failed_checks": dimension_audit.get("failed_checks", []),
                "issues": issues,
                "warnings": warnings,
                "audit_comment": semantic_audit.get("audit_comment", ""),
                "rescore_instruction": (
                    "请针对上述审核不通过原因重新评分。重点修正证据可追溯性、"
                    "量规匹配、分数—理由一致性，以及汇总评价与均值一致性问题。"
                ),
            }

        return feedback

    def _build_final_payload(
        self,
        *,
        state: Dict[str, Any],
        audit_passed: bool,
        audit_records: List[Dict[str, Any]],
        max_review_rounds_reached: bool = False,
    ) -> Dict[str, Any]:
        dimension_results = _to_plain(state.get("dimension_results", {}))
        if not isinstance(dimension_results, dict):
            dimension_results = {}

        last_audit = audit_records[-1] if audit_records else {"failed_dimension_keys": []}
        failed_dimension_keys = list(last_audit.get("failed_dimension_keys", []))
        dimension_summary = build_dimension_summary(dimension_results)

        if audit_passed and int(state.get("review_round", 0)) == 0:
            output_mode = "verified"
            audit_status = "审核通过"
        elif audit_passed:
            output_mode = "auto_resolved"
            audit_status = "自动重评后审核通过"
        else:
            output_mode = "conservative_output"
            audit_status = "未完全通过，系统保守输出"

        return {
            "audit_passed": audit_passed,
            "audit_status": audit_status,
            "output_mode": output_mode,
            "auto_resolved": output_mode in {"auto_resolved", "conservative_output"},
            "review_rounds_used": state.get("review_round", 0),
            "max_review_rounds": state.get("max_review_rounds", self.max_review_rounds),
            "max_review_rounds_reached": max_review_rounds_reached,
            "failed_dimension_keys": failed_dimension_keys,
            "dimension_average_scores": {
                item["dimension_key"]: item.get("mean")
                for item in dimension_summary
            },
            "dimension_summary": dimension_summary,
            "overall_explanation": build_overall_explanation(
                audit_passed=audit_passed,
                dimension_summary=dimension_summary,
                audit_records=audit_records,
                max_review_rounds_reached=max_review_rounds_reached,
            ),
            "audit_records": audit_records,
            "dimension_results": dimension_results,
        }

    def invoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state = dict(state or {})
        state.setdefault("review_round", 0)
        state.setdefault("audit_history", [])
        state.setdefault("verbose", True)

        max_review_rounds = state.get("max_review_rounds", self.max_review_rounds)

        unlimited = max_review_rounds is None
        if not unlimited:
            try:
                max_review_rounds_int = int(max_review_rounds)
                unlimited = max_review_rounds_int < 0
            except Exception:
                max_review_rounds_int = int(self.max_review_rounds or 0)
        else:
            max_review_rounds_int = -1

        audit_records: List[Dict[str, Any]] = list(state.get("audit_history", []))

        while True:
            current_round = int(state.get("review_round", 0))
            pending_audit_keys = state.get("pending_audit_dimension_keys")
            self._verbose_print(state, f"[creativity_Review] 开始第 {current_round} 轮审核")

            if pending_audit_keys:
                self._verbose_print(
                    state,
                    f"[creativity_Review] 本轮只重新审核上一轮未通过并已重评的维度：{pending_audit_keys}",
                )
                audit_result = self.audit_all_dimensions(state, dimension_keys=list(pending_audit_keys))
            else:
                audit_result = self.audit_all_dimensions(state)
            audit_result["review_round"] = current_round
            audit_records.append(audit_result)
            state["audit_history"] = audit_records

            if audit_result.get("passed", False):
                if pending_audit_keys:
                    self._verbose_print(state, "[creativity_Review] 本轮重评维度审核通过；此前已通过维度不再重复审核")
                else:
                    self._verbose_print(state, "[creativity_Review] 审核全部通过")
                state["final_payload"] = self._build_final_payload(
                    state=state,
                    audit_passed=True,
                    audit_records=audit_records,
                    max_review_rounds_reached=False,
                )
                return state

            failed_keys = list(audit_result.get("failed_dimension_keys", []))
            state["failed_dimension_keys"] = failed_keys

            audit_feedback = self._build_rescore_feedback(audit_result)
            state["audit_feedback"] = audit_feedback

            if not failed_keys:
                self._verbose_print(state, "[creativity_Review] 审核未通过但没有可重评维度，进入保守输出")
                state["final_payload"] = self._build_final_payload(
                    state=state,
                    audit_passed=False,
                    audit_records=audit_records,
                    max_review_rounds_reached=False,
                )
                return state

            if (not unlimited) and current_round >= max_review_rounds_int:
                self._verbose_print(
                    state,
                    f"[creativity_Review] 达到最大自动重评轮数 {max_review_rounds_int}，进入保守输出",
                )
                state["final_payload"] = self._build_final_payload(
                    state=state,
                    audit_passed=False,
                    audit_records=audit_records,
                    max_review_rounds_reached=True,
                )
                return state

            self._verbose_print(
                state,
                f"[creativity_Review] 审核未通过，要求重评维度：{failed_keys}",
            )

            rescore_state = dict(state)
            rescore_state["failed_dimension_keys"] = failed_keys
            rescore_state["audit_feedback"] = audit_feedback
            rescore_state["review_round"] = current_round + 1

            rescore_update = self.scoring_fn(rescore_state) or {}
            new_dimension_results = _to_plain(rescore_update.get("dimension_results", {}))
            if not isinstance(new_dimension_results, dict) or not new_dimension_results:
                self._verbose_print(
                    state,
                    "[creativity_Review] 重评函数没有返回新的 dimension_results，进入保守输出",
                )
                state["final_payload"] = self._build_final_payload(
                    state=state,
                    audit_passed=False,
                    audit_records=audit_records,
                    max_review_rounds_reached=False,
                )
                return state

            old_dimension_results = _to_plain(state.get("dimension_results", {}))
            if not isinstance(old_dimension_results, dict):
                old_dimension_results = {}

            old_dimension_results.update(new_dimension_results)
            state["dimension_results"] = old_dimension_results
            state["review_round"] = current_round + 1
            state["pending_audit_dimension_keys"] = list(new_dimension_results.keys())


def build_independent_audit_agent(
    audit_llm: Any,
    scoring_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    max_review_rounds: Optional[int] = 2,
    cv_threshold: float = DEFAULT_CV_THRESHOLD,
) -> IndependentAuditAgent:
    """
    构建独立审核智能体。

    参数：
    - audit_llm: DeepSeekClient 或任何具备 chat_json 方法的对象。
    - scoring_fn: 失败维度重评函数。
    - max_review_rounds: 最大自动重评轮数；None 或负数表示不设上限。
    - cv_threshold: CV 通过阈值，默认 0.20。
    """
    return IndependentAuditAgent(
        audit_llm=audit_llm,
        scoring_fn=scoring_fn,
        max_review_rounds=max_review_rounds,
        cv_threshold=cv_threshold,
    )