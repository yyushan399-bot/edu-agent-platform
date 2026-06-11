"""为 evaluations 表添加 file_url 列（已有库升级用）。"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
for path in (PROJECT_ROOT, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from sqlalchemy import inspect, text  # noqa: E402

from database.base import engine  # noqa: E402


def main() -> None:
    inspector = inspect(engine)
    if "evaluations" not in inspector.get_table_names():
        print("evaluations 表不存在，请先运行 init_db.py")
        return

    columns = {col["name"] for col in inspector.get_columns("evaluations")}
    if "file_url" in columns:
        print("file_url 列已存在，跳过")
        return

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE evaluations ADD COLUMN file_url VARCHAR(512)"))
    print("已添加 evaluations.file_url 列")


if __name__ == "__main__":
    main()
