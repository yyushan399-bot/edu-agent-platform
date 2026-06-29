"""导出 data/section_rag/section_graphrag.json（GraphRAG JSON 降级文件）。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.section_graphrag_service import export_section_graphrag_json


def main() -> None:
    path = export_section_graphrag_json()
    print(f"exported: {path}")


if __name__ == "__main__":
    main()
