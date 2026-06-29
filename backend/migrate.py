"""轻量 SQLite 结构补丁（无 Alembic 时补列）。"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from backend.database import engine

logger = logging.getLogger(__name__)


def run_lightweight_migrations() -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    try:
        insp = inspect(engine)
        if not insp.has_table("projects"):
            return
        cols = {c["name"] for c in insp.get_columns("projects")}
        with engine.begin() as conn:
            if "group_size" not in cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN group_size INTEGER"))
                logger.info("已为 projects 表添加 group_size 列")
        if insp.has_table("group_pbl_evaluations"):
            pbl_cols = {c["name"] for c in insp.get_columns("group_pbl_evaluations")}
            with engine.begin() as conn:
                if "file_path" not in pbl_cols:
                    conn.execute(
                        text("ALTER TABLE group_pbl_evaluations ADD COLUMN file_path VARCHAR(512)")
                    )
                    logger.info("已为 group_pbl_evaluations 表添加 file_path 列")
        if insp.has_table("peer_assessments"):
            peer_cols = {c["name"] for c in insp.get_columns("peer_assessments")}
            with engine.begin() as conn:
                if "group_pbl_evaluation_id" not in peer_cols:
                    conn.execute(
                        text(
                            "ALTER TABLE peer_assessments "
                            "ADD COLUMN group_pbl_evaluation_id INTEGER "
                            "REFERENCES group_pbl_evaluations(id)"
                        )
                    )
                    logger.info("已为 peer_assessments 表添加 group_pbl_evaluation_id 列")
                if "ai_analyze_submission_id" not in peer_cols:
                    conn.execute(
                        text(
                            "ALTER TABLE peer_assessments "
                            "ADD COLUMN ai_analyze_submission_id INTEGER "
                            "REFERENCES ai_analyze_submissions(id)"
                        )
                    )
                    logger.info("已为 peer_assessments 表添加 ai_analyze_submission_id 列")
    except Exception as exc:
        logger.warning("轻量迁移跳过: %s", exc)
