"""
一级指标汇总 Agent（从 preview-agent 迁移）。

将 12 个二级 dimension_summary 汇总为 3 个一级指标评价。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from agents.group_project.pbl_config import DEFAULT_MODEL
from agents.group_project.scoring_models import DeepSeekClient

logger = logging.getLogger(__name__)

PRIMARY_INDICATOR_GROUPS: List[Dict[str, Any]] = [
    {
        "primary_indicator_name": "创造性思维",
        "secondary_dimensions": ["问题提出", "方案新颖性", "创新表征", "创新表达"],
    },
    {
        "primary_indicator_name": "问题解决能力",
        "secondary_dimensions": ["问题界定", "方案建构", "方案实施", "反思调节"],
    },
    {
        "primary_indicator_name": "批判性思维",
        "secondary_dimensions": ["证据分析", "数据分析", "逻辑推演", "局限性评价"],
    },
]


def normalize_dimension_name(name: str) -> str:
    return re.sub(r"\s+", "", str(name or "").strip())


def _parse_score(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _round_score(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value, 2)


def _normalize_primary_match_key(name: str) -> str:
    n = re.sub(r"\s+", "", str(name or "").strip())
    if n in ("问题解决", "问题解决能力"):
        return "问题解决能力"
    return n


def _fallback_primary_comment(primary_name: str, children: List[Dict[str, Any]]) -> Dict[str, str]:
    strength_lines: List[str] = []
    weakness_lines: List[str] = []
    suggestion_lines: List[str] = []
    all_comments: List[str] = []

    for item in children:
        comment = str(item.get("summary_comment", "")).strip()
        if not comment:
            continue
        dim = str(item.get("dimension_name", "")).strip()
        line = f"{dim}：{comment}" if dim else comment
        all_comments.append(line)
        score = _parse_score(item.get("mean"))
        if score is None:
            strength_lines.append(line)
        elif score >= 3.5:
            strength_lines.append(line)
        elif score <= 2.5:
            weakness_lines.append(line)
        else:
            suggestion_lines.append(line)

    if not all_comments:
        return {
            "advantages": "",
            "disadvantages": "",
            "improvement_suggestions": "",
            "summary_comment": "",
        }

    return {
        "advantages": "；".join(strength_lines[:4])[:260],
        "disadvantages": "；".join(weakness_lines[:4])[:260],
        "improvement_suggestions": "；".join(suggestion_lines[:4])[:260],
        "summary_comment": "；".join(all_comments[:4])[:320],
    }


def _calculate_primary_indicator_summary(
    dimension_summary: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_name = {
        normalize_dimension_name(str(item.get("dimension_name", ""))): item
        for item in dimension_summary
        if isinstance(item, dict)
    }

    output: List[Dict[str, Any]] = []
    for group in PRIMARY_INDICATOR_GROUPS:
        children: List[Dict[str, Any]] = []
        scores: List[float] = []
        for dimension_name in group["secondary_dimensions"]:
            normalized_name = normalize_dimension_name(dimension_name)
            raw = by_name.get(normalized_name, {})
            score = _parse_score(raw.get("mean"))
            if score is not None:
                scores.append(score)
            children.append(
                {
                    "dimension_name": normalized_name,
                    "mean": raw.get("mean"),
                    "summary_comment": raw.get("summary_comment", ""),
                }
            )

        mean = _round_score(sum(scores) / len(scores)) if scores else None
        fallback = _fallback_primary_comment(group["primary_indicator_name"], children)
        output.append(
            {
                "primary_indicator_name": group["primary_indicator_name"],
                "mean": mean,
                "advantages": fallback["advantages"],
                "disadvantages": fallback["disadvantages"],
                "improvement_suggestions": fallback["improvement_suggestions"],
                "summary_comment": fallback["summary_comment"],
                "secondary_dimensions": children,
            }
        )
    return output


def _safe_json_object(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _summarize_primary_indicators_with_llm(
    *,
    primary_summary: List[Dict[str, Any]],
    model: str,
) -> List[Dict[str, Any]]:
    system_prompt = """
你是学生报告评价结果汇总智能体。

你的任务：
根据每个一级指标下属二级指标的 summary_comment，概括该一级指标的优点、缺点和改进方向。

严格要求：
1. 不重新评分。
2. 不改变一级指标 mean。
3. 不输出 12 个二级指标的逐项详情。
4. 不能虚构报告中不存在的信息。
5. 优点、缺点、改进方向都要来自下属二级指标评价文本的综合归纳。
6. 输出必须是 JSON object，不要输出 Markdown。
""".strip()

    user_prompt = f"""
# 一级指标及其下属二级指标评价
{json.dumps(primary_summary, ensure_ascii=False, indent=2)}

请输出 3 个一级指标的汇总结果，格式为 primary_indicator_summary 数组。
""".strip()

    try:
        llm = DeepSeekClient(model=model, max_tokens=2400)
        raw = llm.chat_json(system_prompt, user_prompt, temperature=0.2)
    except Exception as exc:
        logger.warning("一级指标 LLM 汇总失败，使用规则兜底：%s", exc)
        return primary_summary

    if not isinstance(raw, dict):
        raw = _safe_json_object(str(raw))

    generated = raw.get("primary_indicator_summary", [])
    generated_by_name: Dict[str, Dict[str, Any]] = {}
    for item in generated:
        if not isinstance(item, dict):
            continue
        key = _normalize_primary_match_key(str(item.get("primary_indicator_name", "")))
        if key:
            generated_by_name[key] = item

    merged: List[Dict[str, Any]] = []
    for item in primary_summary:
        name = str(item.get("primary_indicator_name", ""))
        llm_item = generated_by_name.get(_normalize_primary_match_key(name), {})
        merged_item = dict(item)
        for key in ["advantages", "disadvantages", "improvement_suggestions", "summary_comment"]:
            value = str(llm_item.get(key, "")).strip()
            if value:
                merged_item[key] = value
        merged.append(merged_item)
    return merged


def build_primary_indicator_summary(
    *,
    dimension_summary: List[Dict[str, Any]],
    model: str = DEFAULT_MODEL,
) -> List[Dict[str, Any]]:
    primary_summary = _calculate_primary_indicator_summary(dimension_summary)
    return _summarize_primary_indicators_with_llm(
        primary_summary=primary_summary,
        model=model,
    )


def calculate_primary_indicator_summary(
    dimension_summary: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """按 12 维均分等权汇总三维度（不调用 LLM，供教师截止前改分后同步给组长）。"""
    return _calculate_primary_indicator_summary(dimension_summary)


__all__ = [
    "PRIMARY_INDICATOR_GROUPS",
    "build_primary_indicator_summary",
    "calculate_primary_indicator_summary",
    "normalize_dimension_name",
]
