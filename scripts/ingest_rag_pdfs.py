"""命令行：按域（theory/practice/data）将 PDF 入库 Chroma。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.data_rag import ingest_data_pdf, ingest_data_pdf_directory
from rag.practice_rag import ingest_practice_pdf, ingest_practice_pdf_directory
from rag.theory_rag import ingest_theory_pdf, ingest_theory_pdf_directory

INGESTORS = {
    "theory": (ingest_theory_pdf, ingest_theory_pdf_directory),
    "practice": (ingest_practice_pdf, ingest_practice_pdf_directory),
    "data": (ingest_data_pdf, ingest_data_pdf_directory),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG PDF 入库（bge-m3 + Chroma）")
    parser.add_argument(
        "domain",
        choices=["theory", "practice", "data"],
        help="知识库域",
    )
    parser.add_argument("path", help="PDF 文件或目录路径")
    parser.add_argument("--recursive", action="store_true", help="目录递归扫描")
    args = parser.parse_args()

    ingest_file, ingest_dir = INGESTORS[args.domain]
    target = Path(args.path)

    if target.is_file():
        ids = ingest_file(target)
    elif target.is_dir():
        ids = ingest_dir(target, recursive=args.recursive)
    else:
        raise SystemExit(f"路径不存在: {target}")

    print(f"域={args.domain} 已入库 chunks={len(ids)} 路径={target}")


if __name__ == "__main__":
    main()
