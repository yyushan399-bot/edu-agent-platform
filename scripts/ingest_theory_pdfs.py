"""命令行：将 PDF 入库 theory 知识库（Chroma + bge-m3）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 保证可导入项目根模块
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.theory_rag import TheoryRAG, ingest_theory_pdf, ingest_theory_pdf_directory


def main() -> None:
    parser = argparse.ArgumentParser(description="理论 PDF 入库到 Chroma theory collection")
    parser.add_argument("path", help="PDF 文件路径或目录路径")
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="目录模式下递归扫描子目录",
    )
    args = parser.parse_args()
    target = Path(args.path)

    if target.is_file():
        ids = ingest_theory_pdf(target)
        print(f"已入库文件: {target}，共 {len(ids)} 个文本块")
    elif target.is_dir():
        ids = ingest_theory_pdf_directory(target, recursive=args.recursive)
        print(f"已入库目录: {target}，共 {len(ids)} 个文本块")
    else:
        raise SystemExit(f"路径不存在: {target}")

    rag = TheoryRAG()
    print(f"嵌入模型: {rag.embedding_model}")
    print(f"持久化目录: {rag.manager.persist_directory}")


if __name__ == "__main__":
    main()
