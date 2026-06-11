"""教育智能体 CLI：多模态文件或纯文本，经 app.invoke 执行 LangGraph。"""

from __future__ import annotations

import argparse
import json
import sys

import llm_config  # noqa: F401
from llm_config import is_dotenv_loaded

from input.multimodal_processor import MultimodalProcessor, supported_extensions
from main_graph import app
from state import create_initial_state, normalize_routes


def _read_text_input() -> str:
    print("请输入学生提交内容（单独一行输入 END 结束）：")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def run_graph(
    student_input: str,
    uploaded_files=None,
    *,
    routes: list[str] | None = None,
    student_id: str | None = None,
    memory_k: int = 3,
) -> None:
    initial = create_initial_state(
        student_input,
        uploaded_files=uploaded_files,
        routes=routes,
        student_id=student_id,
        memory_retrieve_k=memory_k,
    )
    if student_id:
        print(f"长期记忆: student_id={student_id}（图内 retrieve/save 节点处理）")

    result = app.invoke(initial)
    active = result.get("routes") or []
    saved_id = result.get("last_saved_evaluation_id")
    if saved_id:
        print(f"已写入长期记忆: evaluation_id={saved_id}")

    print(f"\n===== 执行结果（路由: {', '.join(active)}）=====\n")
    print(json.dumps(dict(result), ensure_ascii=False, indent=2))


def main() -> None:
    if not is_dotenv_loaded():
        print("错误：未检测到 OPENAI_API_KEY，请配置 .env 后重试。", file=sys.stderr)
        sys.exit(1)

    exts = ", ".join(supported_extensions())
    parser = argparse.ArgumentParser(
        description=f"教育智能体：多模态输入（{exts}）或纯文本"
    )
    parser.add_argument(
        "--file",
        action="append",
        dest="files",
        metavar="PATH",
        help="文件路径，可多次指定以合并（pdf/docx/png/jpg/jpeg）",
    )
    parser.add_argument(
        "--pdf",
        type=str,
        help="（兼容）单个 PDF，等同于 --file",
    )
    parser.add_argument(
        "--text",
        type=str,
        help="直接传入文本；可与 --file 组合为补充说明",
    )
    parser.add_argument(
        "--routes",
        type=str,
        help="预设路由，逗号分隔，如 theory,data（跳过 LLM 路由）",
    )
    parser.add_argument(
        "--student-id",
        type=str,
        help="学生 ID，启用 JSON 长期记忆（每 ID 一个文件）",
    )
    parser.add_argument(
        "--memory-k",
        type=int,
        default=3,
        help="注入的历史评估条数（默认 3）",
    )
    args = parser.parse_args()

    preset_routes: list[str] | None = None
    if args.routes:
        preset_routes = normalize_routes(
            [r.strip() for r in args.routes.split(",") if r.strip()]
        )

    file_list: list[str] = list(args.files or [])
    if args.pdf:
        file_list.append(args.pdf)

    if file_list:
        extra = args.text.strip() if args.text else None
        result = MultimodalProcessor.process(file_list, extra_text=extra)
        student_input = result.to_student_input()
        print(
            f"已加载 {len(file_list)} 个文件"
            f"（约 {len(student_input)} 字符，模态: {', '.join(result.modalities)}）"
        )
        run_graph(
            student_input,
            result.uploaded_files,
            routes=preset_routes,
            student_id=args.student_id,
            memory_k=args.memory_k,
        )
        return

    if args.text:
        text = args.text.strip()
        if not text:
            print("错误：--text 不能为空。", file=sys.stderr)
            sys.exit(1)
        student_input, _ = MultimodalProcessor.load_for_graph(text)
        run_graph(
            student_input,
            routes=preset_routes,
            student_id=args.student_id,
            memory_k=args.memory_k,
        )
        return

    text = _read_text_input()
    if not text:
        print("错误：输入不能为空。", file=sys.stderr)
        sys.exit(1)
    run_graph(
        text,
        routes=preset_routes,
        student_id=args.student_id,
        memory_k=args.memory_k,
    )


if __name__ == "__main__":
    main()
