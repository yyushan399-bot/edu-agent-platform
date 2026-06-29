"""评估流水线 —— 编排多智能体评分 + 元评估."""

import json
import sys
import os
from typing import Optional

from sqlalchemy.orm import Session

# 把上级目录加入 Python 路径，让 prompts / rubrics 能被 import
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".."))

from backend.models import Submission, Evaluation, MetaReport, SubmissionStatus
from backend.services.llm_client import LLMClient


def run_evaluation(submission: Submission, db: Session) -> dict:
    """对一次提交运行完整的评估流水线.

    Returns:
        {"evaluations": [...], "meta_report": {...}}
    """
    content = submission.text_content or ""
    if submission.file_path and os.path.exists(submission.file_path):
        with open(submission.file_path, "r", encoding="utf-8", errors="ignore") as f:
            content += "\n" + f.read()

    if not content.strip():
        raise ValueError("提交内容为空，无法评估")

    # ── 1. 确定哪些维度需要评估（基于 content 自动路由）──
    active_dims = _detect_active_dimensions(content)

    # ── 2. 各维度 Agent 评分 ──
    llm = LLMClient()
    eval_results = []

    for dim_key in active_dims:
        result = llm.evaluate_dimension(dim_key, content)
        if result:
            evaluation = Evaluation(
                submission_id=submission.id,
                dim_key=dim_key,
                scores=result.get("scores"),
                feedbacks=result.get("feedbacks"),
                summary=result.get("summary"),
                dimension_score=result.get("dimension_score"),
            )
            db.add(evaluation)
            db.flush()
            eval_results.append(result)

    # ── 3. 计算总分 ──
    dim_scores = [
        r.get("dimension_score", 0) or 0
        for r in eval_results
        if r.get("dimension_score") is not None
    ]
    total_score = round(sum(dim_scores) / len(dim_scores), 2) if dim_scores else 0

    # ── 4. 生成元评估报告 ──
    scores_detail = {r.get("dim_key", d): r for r, d in zip(eval_results, active_dims)}
    report_content = llm.generate_meta_report(scores_detail, total_score)

    meta_report = MetaReport(
        submission_id=submission.id,
        total_score=total_score,
        report_content=report_content,
    )
    db.add(meta_report)
    db.commit()

    return {
        "evaluations": eval_results,
        "meta_report": {"total_score": total_score, "report": report_content},
    }


def _detect_active_dimensions(content: str) -> list[str]:
    """根据学生提交内容自动路由维度。"""
    # 简单启发式规则
    keywords = {
        "theory": ["理论", "概念", "框架", "文献", "定义", "theory", "concept"],
        "practice": ["实践", "实现", "方案", "设计", "部署", "开发", "practice", "implementation"],
        "data": ["数据", "采集", "分析", "可视化", "实验", "data", "analysis", "statistics"],
        "literature": ["文献", "综述", "观点", "批判", "研究现状", "literature", "review"],
    }

    active = ["theory", "practice", "data", "literature"]  # 默认全部
    # 简化版本：如果内容太短或者没有明显关键词，返回全部
    return active
