"""Neo4j / JSON 双后端 GraphRAG 检索服务（章节 × 指标权重）。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal, Protocol

from data.section_rag.graphrag_config import (
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    SECTION_GRAPHRAG_BACKEND,
    SECTION_GRAPHRAG_JSON_PATH,
    neo4j_configured,
)
from data.section_rag.rubrics import RUBRIC_BY_CRITERION
from data.section_rag.section_weights import SECTION_CRITERIA_WEIGHTS
from utils.section_constants import SECTION_NAMES

try:
    from neo4j import GraphDatabase
except ImportError:  # pragma: no cover - optional dependency
    GraphDatabase = None  # type: ignore[misc, assignment]

GraphRAGBackend = Literal["neo4j", "json"]
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_JSON_PATH = _PROJECT_ROOT / "data" / "section_rag" / "section_graphrag.json"


class SectionGraphRAGRetriever(Protocol):
    backend_name: GraphRAGBackend

    def close(self) -> None: ...

    def get_section_criteria(self, section_name: str) -> list[dict[str, Any]]: ...

    def get_criterion_rubrics(self, criterion_name: str) -> dict[int, str]: ...

    def get_criterion_exemplars(
        self,
        criterion_name: str,
        section_name: str,
    ) -> dict[int, list[dict[str, Any]]]: ...

    def retrieve_full_context(self, section_name: str) -> dict[str, Any]: ...


def default_graphrag_json_path() -> Path:
    raw = os.getenv("SECTION_GRAPHRAG_JSON_PATH", SECTION_GRAPHRAG_JSON_PATH).strip()
    if raw:
        return Path(raw)
    return _DEFAULT_JSON_PATH


def build_section_graphrag_snapshot() -> dict[str, Any]:
    """从内置静态数据构建 GraphRAG JSON 快照。"""
    rubrics = {
        criterion: {str(score): text for score, text in scores.items()}
        for criterion, scores in RUBRIC_BY_CRITERION.items()
    }
    section_criteria = {
        section: [
            {"criterion_name": name, "weight": weight}
            for name, weight in weights
        ]
        for section, weights in SECTION_CRITERIA_WEIGHTS.items()
    }
    return {
        "version": 1,
        "source": "empty-window-static",
        "sections": SECTION_NAMES,
        "rubrics": rubrics,
        "section_criteria": section_criteria,
    }


def export_section_graphrag_json(path: str | Path | None = None) -> Path:
    """导出 JSON 降级文件（方案 B）。"""
    target = Path(path) if path else default_graphrag_json_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(build_section_graphrag_snapshot(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def _load_json_snapshot(path: Path) -> dict[str, Any]:
    if not path.is_file():
        export_section_graphrag_json(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "section_criteria" not in payload or "rubrics" not in payload:
        raise ValueError(f"GraphRAG JSON 格式无效：{path}")
    return payload


class GraphRAGRetriever:
    """从 Neo4j GraphRAG 检索章节评分上下文。"""

    backend_name: GraphRAGBackend = "neo4j"

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        if GraphDatabase is None:
            raise ImportError("未安装 neo4j 驱动。请执行: pip install neo4j")
        self.uri = uri or NEO4J_URI
        self.user = user or NEO4J_USER
        self.password = password if password is not None else NEO4J_PASSWORD
        if not self.password:
            raise ValueError("未配置 NEO4J_PASSWORD。请在 .env 中设置 Neo4j 连接信息。")
        self.driver = GraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password),
        )

    def close(self) -> None:
        self.driver.close()

    def __enter__(self) -> GraphRAGRetriever:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def verify_connection(self) -> None:
        with self.driver.session() as session:
            session.run("RETURN 1").consume()

    def get_section_criteria(self, section_name: str) -> list[dict[str, Any]]:
        query = """
        MATCH (s:ReportSection {name: $section_name})<-[e:EVALUATES]-(c:Criterion)
        RETURN c.name AS criterion_name, e.weight AS weight
        ORDER BY e.weight DESC
        """
        with self.driver.session() as session:
            result = session.run(query, section_name=section_name)
            return [dict(record) for record in result]

    def get_criterion_rubrics(self, criterion_name: str) -> dict[int, str]:
        query = """
        MATCH (c:Criterion {name: $criterion_name})-[:HAS_DESCRIPTOR]->(sd:ScoreDescriptor)
        RETURN sd.score AS score, sd.description AS description
        ORDER BY sd.score DESC
        """
        with self.driver.session() as session:
            result = session.run(query, criterion_name=criterion_name)
            return {record["score"]: record["description"] for record in result}

    def get_criterion_exemplars(
        self,
        criterion_name: str,
        section_name: str,
    ) -> dict[int, list[dict[str, Any]]]:
        query = """
        MATCH (c:Criterion {name: $criterion_name})-[:HAS_DESCRIPTOR]->(sd:ScoreDescriptor)
        OPTIONAL MATCH (sd)<-[ex:EXEMPLIFIES]-(chunk:ReportChunk)
        WHERE chunk.source_section = $section_name
        RETURN sd.score AS score,
               collect(DISTINCT {
                   content: chunk.content,
                   reason: ex.reason,
                   source_report: chunk.source_report,
                   quality_tag: chunk.quality_tag
               })[0..2] AS exemplars
        ORDER BY sd.score DESC
        """
        with self.driver.session() as session:
            result = session.run(
                query,
                criterion_name=criterion_name,
                section_name=section_name,
            )
            exemplars_by_score: dict[int, list[dict[str, Any]]] = {}
            for record in result:
                score = record["score"]
                exemplars = [ex for ex in record["exemplars"] if ex.get("content")]
                if exemplars:
                    exemplars_by_score[score] = exemplars
            return exemplars_by_score

    def retrieve_full_context(self, section_name: str) -> dict[str, Any]:
        criteria = self.get_section_criteria(section_name)
        full_context: dict[str, Any] = {"section_name": section_name, "criteria": []}
        for crit in criteria:
            criterion_name = crit["criterion_name"]
            weight = crit["weight"]
            rubrics = self.get_criterion_rubrics(criterion_name)
            exemplars = self.get_criterion_exemplars(criterion_name, section_name)
            full_context["criteria"].append(
                {
                    "criterion_name": criterion_name,
                    "weight": weight,
                    "rubrics": rubrics,
                    "exemplars": exemplars,
                }
            )
        return full_context


class JsonGraphRAGRetriever:
    """JSON 静态快照检索器（无 Neo4j / 无 exemplar 图遍历）。"""

    backend_name: GraphRAGBackend = "json"

    def __init__(self, json_path: str | Path | None = None):
        self.json_path = Path(json_path) if json_path else default_graphrag_json_path()
        self.snapshot = _load_json_snapshot(self.json_path)
        self.section_criteria: dict[str, list[dict[str, Any]]] = self.snapshot[
            "section_criteria"
        ]
        self.rubrics: dict[str, dict[int, str]] = {
            criterion: {int(score): text for score, text in scores.items()}
            for criterion, scores in self.snapshot["rubrics"].items()
        }

    def close(self) -> None:
        return None

    def __enter__(self) -> JsonGraphRAGRetriever:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def verify_connection(self) -> None:
        if not self.section_criteria:
            raise ValueError("GraphRAG JSON 快照为空。")

    def get_section_criteria(self, section_name: str) -> list[dict[str, Any]]:
        items = list(self.section_criteria.get(section_name, []))
        return sorted(items, key=lambda item: item["weight"], reverse=True)

    def get_criterion_rubrics(self, criterion_name: str) -> dict[int, str]:
        return dict(self.rubrics.get(criterion_name, {}))

    def get_criterion_exemplars(
        self,
        criterion_name: str,
        section_name: str,
    ) -> dict[int, list[dict[str, Any]]]:
        return {}

    def retrieve_full_context(self, section_name: str) -> dict[str, Any]:
        if section_name not in SECTION_NAMES:
            raise ValueError(f"未知章节：{section_name}")
        full_context: dict[str, Any] = {"section_name": section_name, "criteria": []}
        for crit in self.get_section_criteria(section_name):
            criterion_name = crit["criterion_name"]
            full_context["criteria"].append(
                {
                    "criterion_name": criterion_name,
                    "weight": crit["weight"],
                    "rubrics": self.get_criterion_rubrics(criterion_name),
                    "exemplars": {},
                }
            )
        return full_context


def json_graphrag_available() -> bool:
    path = default_graphrag_json_path()
    if path.is_file():
        return True
    try:
        build_section_graphrag_snapshot()
        return True
    except Exception:
        return False


def probe_neo4j_graphrag() -> tuple[bool, str | None]:
    if not neo4j_configured():
        return False, "Neo4j 未配置（缺少 NEO4J_PASSWORD）"
    try:
        with GraphRAGRetriever() as retriever:
            retriever.verify_connection()
            criteria = retriever.get_section_criteria(SECTION_NAMES[0])
            if not criteria:
                return False, "Neo4j 已连接但未找到章节图谱数据，请执行 graphrag_schema.cypher"
        return True, None
    except Exception as exc:
        return False, str(exc)


def probe_graphrag_health() -> dict[str, Any]:
    """探测 GraphRAG 可用性与实际后端。"""
    backend_pref = os.getenv("SECTION_GRAPHRAG_BACKEND", SECTION_GRAPHRAG_BACKEND).lower()
    info: dict[str, Any] = {
        "graphrag_available": False,
        "graphrag_backend": None,
        "graphrag_configured": False,
        "graphrag_error": None,
        "neo4j_configured": neo4j_configured(),
        "json_fallback_available": json_graphrag_available(),
        "backend_preference": backend_pref,
    }

    if backend_pref == "json":
        if not info["json_fallback_available"]:
            info["graphrag_error"] = "JSON 快照不可用"
            return info
        info.update(
            graphrag_available=True,
            graphrag_backend="json",
            graphrag_configured=True,
        )
        return info

    if backend_pref == "neo4j":
        ok, err = probe_neo4j_graphrag()
        info["graphrag_available"] = ok
        info["graphrag_configured"] = neo4j_configured()
        info["graphrag_backend"] = "neo4j" if ok else None
        info["graphrag_error"] = err
        return info

    ok, err = probe_neo4j_graphrag()
    if ok:
        info.update(
            graphrag_available=True,
            graphrag_backend="neo4j",
            graphrag_configured=True,
        )
        return info

    if info["json_fallback_available"]:
        info.update(
            graphrag_available=True,
            graphrag_backend="json",
            graphrag_configured=True,
            graphrag_error=f"Neo4j 不可用，已降级 JSON：{err}",
        )
        return info

    info["graphrag_error"] = err or "GraphRAG 不可用"
    return info


def create_section_retriever(
    backend: str | None = None,
) -> SectionGraphRAGRetriever:
    """按配置创建 GraphRAG 检索器（auto 优先 Neo4j，失败降级 JSON）。"""
    backend_pref = (backend or os.getenv("SECTION_GRAPHRAG_BACKEND", SECTION_GRAPHRAG_BACKEND)).lower()

    if backend_pref == "json":
        retriever = JsonGraphRAGRetriever()
        retriever.verify_connection()
        return retriever

    if backend_pref == "neo4j":
        if not neo4j_configured():
            raise ValueError(
                "Neo4j 未配置。请设置 NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD。"
            )
        retriever = GraphRAGRetriever()
        retriever.verify_connection()
        return retriever

    if neo4j_configured():
        try:
            retriever = GraphRAGRetriever()
            retriever.verify_connection()
            return retriever
        except Exception:
            pass

    retriever = JsonGraphRAGRetriever()
    retriever.verify_connection()
    return retriever


def create_graphrag_retriever() -> GraphRAGRetriever:
    """兼容阶段 0：仅创建 Neo4j 检索器。"""
    if not neo4j_configured():
        raise ValueError(
            "Neo4j 未配置。请设置 NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD，"
            "或设置 SECTION_GRAPHRAG_BACKEND=json 使用 JSON 降级。"
        )
    retriever = GraphRAGRetriever()
    retriever.verify_connection()
    return retriever


__all__ = [
    "GraphRAGBackend",
    "GraphRAGRetriever",
    "JsonGraphRAGRetriever",
    "SectionGraphRAGRetriever",
    "build_section_graphrag_snapshot",
    "create_graphrag_retriever",
    "create_section_retriever",
    "default_graphrag_json_path",
    "export_section_graphrag_json",
    "json_graphrag_available",
    "neo4j_configured",
    "probe_graphrag_health",
    "probe_neo4j_graphrag",
]
