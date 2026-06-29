from pathlib import Path

src = Path("services/section_graphrag_indexer.py").read_text(encoding="utf-8")
start = src.index("RUBRIC_BY_CRITERION = {")
end = src.index("# ==================== 文件读取 / 章节切分")
block = src[start : end].rstrip()
header = (
    '"""12 二级指标量规（与 graphrag_schema.cypher 一致）。"""\n\n'
    "from __future__ import annotations\n\n"
)
Path("data/section_rag/rubrics.py").write_text(
    header + block + '\n\n__all__ = ["RUBRIC_BY_CRITERION"]\n',
    encoding="utf-8",
)
print("written", Path("data/section_rag/rubrics.py").stat().st_size)
