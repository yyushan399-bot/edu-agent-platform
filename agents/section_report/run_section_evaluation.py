"""章节反馈 CLI：整报告切分 + 单章/多章评分（阶段 0–1）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agents.group_project.pbl_config import DEFAULT_MODEL, DEFAULT_SCORING_TIMES
from agents.group_project.scoring_models import DeepSeekClient
from agents.section_report.section_config import (
    DEFAULT_CV_THRESHOLD,
    DEFAULT_MAX_REVIEW_ROUNDS,
    SECTION_NAMES,
)
from agents.section_report.section_review_agent import run_review_loop
from agents.section_report.section_scoring_agent import score_criteria
from services.section_graphrag_service import create_section_retriever
from utils.section_parser import parse_report_from_path


def _read_text(text: str | None, text_file: str | None) -> str:
    if text_file:
        return Path(text_file).read_text(encoding="utf-8")
    if text:
        return text
    raise ValueError("请提供 --text 或 --text-file")


def _resolve_section_text(args: argparse.Namespace) -> tuple[str, str | None]:
    """
    返回 (section_name, student_text)。
    split-only 模式返回 ("", None)。
    """
    if args.split_only:
        if not args.report_file:
            raise ValueError("--split-only 需要配合 --report-file。")
        return "", None

    if args.report_file:
        parsed = parse_report_from_path(args.report_file)
        if args.section:
            text = parsed.get_section_text(args.section)
            if not text:
                missing = ", ".join(parsed.missing_sections) or "未知"
                raise ValueError(
                    f"报告 {args.report_file} 中未找到章节「{args.section}」。"
                    f" 已识别：{parsed.found_sections}；缺失：{missing}"
                )
            return args.section, text

        raise ValueError(
            "使用 --report-file 时请指定 --section，或改用 --split-only 仅输出切分结果。"
        )

    if not args.section:
        raise ValueError("请指定 --section，或使用 --report-file 上传整份报告。")

    return args.section, _read_text(args.text, args.text_file)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="章节反馈：整报告切分 / GraphRAG 评分 / 审核循环"
    )
    parser.add_argument(
        "--section",
        default=None,
        choices=SECTION_NAMES,
        help="章节名称（整报告模式下指定要评价的章）",
    )
    parser.add_argument("--text", default=None, help="学生章节文本")
    parser.add_argument("--text-file", default=None, help="学生章节文本文件")
    parser.add_argument(
        "--report-file",
        default=None,
        help="整份报告 PDF/DOCX/TXT，配合 --section 或 --split-only",
    )
    parser.add_argument(
        "--split-only",
        action="store_true",
        help="仅切分整报告为 7 章，不调用 LLM/Neo4j",
    )
    parser.add_argument(
        "--mode",
        choices=["score", "review"],
        default="review",
        help="score=仅评分；review=评分+审核循环（默认）",
    )
    parser.add_argument("--out", default="section_report.json", help="输出 JSON 路径")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LLM 模型")
    parser.add_argument(
        "--times",
        type=int,
        default=DEFAULT_SCORING_TIMES,
        help="每指标评分次数",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=DEFAULT_MAX_REVIEW_ROUNDS,
        help="最大审核轮次",
    )
    parser.add_argument(
        "--cv-threshold",
        type=float,
        default=DEFAULT_CV_THRESHOLD,
        help="CV 稳定性阈值",
    )
    args = parser.parse_args(argv)

    if args.split_only:
        parsed = parse_report_from_path(args.report_file)
        payload = parsed.to_dict()
        out_path = Path(args.out)
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"切分完成：识别 {len(parsed.sections)} 章 → {out_path}")
        if parsed.missing_sections:
            print(f"缺失章节：{', '.join(parsed.missing_sections)}")
        return 0

    section_name, student_text = _resolve_section_text(args)
    assert student_text is not None

    retriever = create_section_retriever()
    llm = DeepSeekClient(model=args.model)

    try:
        if args.mode == "score":
            results = score_criteria(
                llm=llm,
                retriever=retriever,
                section_name=section_name,
                student_text=student_text,
                scoring_times=args.times,
            )
            payload = {name: summary.model_dump() for name, summary in results.items()}
        else:
            final_report = run_review_loop(
                section_name=section_name,
                student_text=student_text,
                scoring_llm=llm,
                audit_llm=llm,
                retriever=retriever,
                max_rounds=args.max_rounds,
                scoring_times=args.times,
                cv_threshold=args.cv_threshold,
            )
            payload = final_report.model_dump()

        out_path = Path(args.out)
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n章节「{section_name}」结果已保存：{out_path}")
        return 0
    finally:
        retriever.close()


if __name__ == "__main__":
    sys.exit(main())
