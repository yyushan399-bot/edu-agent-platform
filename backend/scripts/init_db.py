"""初始化数据库表结构。"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
for path in (PROJECT_ROOT, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from database.base import engine, init_db  # noqa: E402


def main() -> None:
    db_path = engine.url.database
    init_db()
    print(f"Database initialized: {db_path}")


if __name__ == "__main__":
    main()
