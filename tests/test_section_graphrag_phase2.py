"""学生反馈 GraphRAG · 阶段 2 单元测试（JSON 降级，无需 Neo4j）。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.section_graphrag_service import (
    JsonGraphRAGRetriever,
    build_section_graphrag_snapshot,
    create_section_retriever,
    export_section_graphrag_json,
    probe_graphrag_health,
)


class TestSectionGraphRAGSnapshot(unittest.TestCase):
    def test_build_snapshot_has_all_sections(self) -> None:
        snapshot = build_section_graphrag_snapshot()
        self.assertEqual(len(snapshot["sections"]), 7)
        self.assertIn("实验实施", snapshot["section_criteria"])
        self.assertIn("方案实施", snapshot["rubrics"])

    def test_export_json_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "section_graphrag.json"
            export_section_graphrag_json(path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], 1)
            retriever = JsonGraphRAGRetriever(path)
            context = retriever.retrieve_full_context("实验实施")
        self.assertEqual(context["section_name"], "实验实施")
        self.assertGreaterEqual(len(context["criteria"]), 2)
        names = {item["criterion_name"] for item in context["criteria"]}
        self.assertIn("方案实施", names)

    def test_experiment_section_weights_and_rubrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "section_graphrag.json"
            export_section_graphrag_json(path)
            retriever = JsonGraphRAGRetriever(path)
            context = retriever.retrieve_full_context("实验实施")

        by_name = {item["criterion_name"]: item for item in context["criteria"]}
        self.assertAlmostEqual(by_name["方案实施"]["weight"], 0.9)
        self.assertIn(5, by_name["方案实施"]["rubrics"])
        self.assertIn(1, by_name["方案实施"]["rubrics"])
        self.assertEqual(by_name["方案实施"]["exemplars"], {})


class TestSectionGraphRAGBackend(unittest.TestCase):
    def test_create_section_retriever_json_backend(self) -> None:
        with patch.dict(
            "os.environ",
            {"SECTION_GRAPHRAG_BACKEND": "json", "NEO4J_PASSWORD": ""},
            clear=False,
        ):
            retriever = create_section_retriever()
            self.assertEqual(retriever.backend_name, "json")
            criteria = retriever.get_section_criteria("文献检索")
            retriever.close()
        self.assertTrue(criteria)

    def test_probe_graphrag_health_json_when_neo4j_missing(self) -> None:
        with patch.dict(
            "os.environ",
            {"SECTION_GRAPHRAG_BACKEND": "auto", "NEO4J_PASSWORD": ""},
            clear=False,
        ):
            info = probe_graphrag_health()
        self.assertTrue(info["graphrag_available"])
        self.assertEqual(info["graphrag_backend"], "json")
        self.assertTrue(info["json_fallback_available"])


if __name__ == "__main__":
    unittest.main()
