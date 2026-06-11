"""LangGraph 教育智能体全局状态定义。"""

from __future__ import annotations

from typing import Annotated, Any, NotRequired, TypedDict

# ---------------------------------------------------------------------------
# 路由常量
# ---------------------------------------------------------------------------

VALID_ROUTES: frozenset[str] = frozenset({"theory", "practice", "data", "literature"})
DEFAULT_ROUTES: list[str] = ["theory"]
ROUTE_LABELS: dict[str, str] = {
    "theory": "理论",
    "practice": "实践",
    "data": "数据",
    "data_analysis": "数据分析",
    "literature": "文献",
}

# LLM Router 输出别名 → 图内 canonical 路由
ROUTE_ALIASES: dict[str, str] = {
    "data_analysis": "data",
    "data-analysis": "data",
}

# ---------------------------------------------------------------------------
# 基础类型
# ---------------------------------------------------------------------------


class HistoryTurn(TypedDict):
    """单轮对话记忆条目。"""

    role: str
    content: str
    turn_id: NotRequired[int]


class UploadedFile(TypedDict, total=False):
    """用户上传文件元信息。"""

    name: str
    path: str
    content_type: NotRequired[str]
    modality: NotRequired[str]
    label: NotRequired[str]


class EvaluationRecord(TypedDict, total=False):
    """单条历史评估记录（与 memory/evaluation_store 持久化结构对齐）。"""

    evaluation_id: str
    timestamp: str
    routes: list[str]
    route: NotRequired[str]
    student_input_preview: str
    theory_result: TheoryResult | str
    practice_result: PracticeResult
    data_result: DataResult
    literature_result: LiteratureResult
    total_score: float | str
    score_detail: dict[str, Any]
    route_reason: NotRequired[str]
    final_feedback: str
    history_memory: list[HistoryTurn]
    uploaded_files: list[UploadedFile]
    extra: NotRequired[dict[str, Any]]


class TheoryResult(TypedDict, total=False):
    concept_understanding: str
    logic: str
    critical_thinking: str
    feedback: str
    score: float


DEFAULT_THEORY_RESULT: TheoryResult = {
    "concept_understanding": "",
    "logic": "",
    "critical_thinking": "",
    "feedback": "",
    "score": 0.0,
}


class PracticeResult(TypedDict, total=False):
    experiment_design: float | str
    operation_standard: float | str
    problem_solving: float | str
    feedback: str
    score: float


DEFAULT_PRACTICE_RESULT: PracticeResult = {
    "experiment_design": 0.0,
    "operation_standard": 0.0,
    "problem_solving": 0.0,
    "feedback": "",
    "score": 0.0,
}


class DataResult(TypedDict, total=False):
    data_analysis: float
    visualization: float
    modeling: float
    feedback: str
    score: float


DEFAULT_DATA_RESULT: DataResult = {
    "data_analysis": 0.0,
    "visualization": 0.0,
    "modeling": 0.0,
    "feedback": "",
    "score": 0.0,
}


class LiteratureResult(TypedDict, total=False):
    """文献阅读评估结果。"""

    summary: str
    student_viewpoint: str
    alignment_analysis: str
    critical_thinking_score: float | str
    innovation_score: float | str
    suggestions: str
    score: float


DEFAULT_LITERATURE_RESULT: LiteratureResult = {
    "summary": "",
    "student_viewpoint": "",
    "alignment_analysis": "",
    "critical_thinking_score": 0.0,
    "innovation_score": 0.0,
    "suggestions": "",
    "score": 0.0,
}


class ScoreDetailItem(TypedDict):
    route: str
    label: str
    score: float


class ScoreDetail(TypedDict, total=False):
    """各路由得分明细及汇总统计。"""

    routes: list[str]
    items: list[ScoreDetailItem]
    scores: dict[str, float]
    count: int
    average: float


DEFAULT_SCORE_DETAIL: ScoreDetail = {
    "routes": [],
    "items": [],
    "scores": {},
    "count": 0,
    "average": 0.0,
}


DEFAULT_RETRIEVED_CONTEXT = ""
DEFAULT_MEMORY_CONTEXT = "（未配置 student_id，无长期记忆。）"
DEFAULT_RESEARCH_CONTEXT = "（未启用深度联网研究。）"
DEFAULT_EVALUATION_HISTORY: list[EvaluationRecord] = []
DEFAULT_UPLOADED_FILES: list[UploadedFile] = []
DEFAULT_CHAT_HISTORY: list[HistoryTurn] = []


# ---------------------------------------------------------------------------
# Reducers
# ---------------------------------------------------------------------------


def append_history(
    existing: list[HistoryTurn] | None,
    update: list[HistoryTurn] | HistoryTurn | None,
) -> list[HistoryTurn]:
    if existing is None:
        existing = []
    if update is None:
        return existing
    if isinstance(update, list):
        return existing + update
    return existing + [update]


def merge_uploaded_files(
    existing: list[UploadedFile] | None,
    update: list[UploadedFile] | UploadedFile | None,
) -> list[UploadedFile]:
    if existing is None:
        existing = []
    if update is None:
        return existing
    items = update if isinstance(update, list) else [update]
    if not items:
        return existing

    seen = {f.get("path", "") for f in existing}
    merged = list(existing)
    for item in items:
        path = item.get("path", "")
        if path and path in seen:
            continue
        if path:
            seen.add(path)
        merged.append(item)
    return merged


def merge_retrieved_contexts(
    existing: dict[str, str] | None,
    update: dict[str, str] | None,
) -> dict[str, str]:
    """按路由键合并 RAG 上下文（多路由并行时各域独立存储）。"""
    if existing is None:
        existing = {}
    if update is None:
        return existing
    return {**existing, **update}


def merge_evaluation_history(
    existing: list[EvaluationRecord] | None,
    update: list[EvaluationRecord] | EvaluationRecord | None,
) -> list[EvaluationRecord]:
    """合并评估历史列表（按 evaluation_id 去重，保持顺序）。"""
    if existing is None:
        existing = []
    if update is None:
        return existing
    items = update if isinstance(update, list) else [update]
    if not items:
        return existing

    seen = {
        str(r.get("evaluation_id", ""))
        for r in existing
        if r.get("evaluation_id")
    }
    merged: list[EvaluationRecord] = list(existing)
    for item in items:
        eid = str(item.get("evaluation_id", ""))
        if eid and eid in seen:
            continue
        if eid:
            seen.add(eid)
        merged.append(item)
    return merged


def merge_routes(
    existing: list[str] | None,
    update: list[str] | str | None,
) -> list[str]:
    """合并路由列表（去重并保持顺序）。"""
    if existing is None:
        existing = []
    if update is None:
        return existing
    items = update if isinstance(update, list) else [update]
    return normalize_routes([*existing, *items])


# ---------------------------------------------------------------------------
# 路由工具
# ---------------------------------------------------------------------------


def normalize_route(route: str | None) -> str:
    """单路由规范化：别名映射 + 校验，非法时回退默认。"""
    raw = str(route or "").strip().lower()
    canonical = ROUTE_ALIASES.get(raw, raw)
    if canonical in VALID_ROUTES:
        return canonical
    return DEFAULT_ROUTES[0]


def normalize_routes(
    routes: list[str] | str | None,
    *,
    legacy_route: str | None = None,
) -> list[str]:
    """规范化路由列表，过滤非法值，保证至少一条。"""
    raw: list[str] = []
    if isinstance(routes, str):
        raw = [routes]
    elif routes:
        raw = list(routes)
    if legacy_route:
        raw.append(legacy_route)

    seen: set[str] = set()
    normalized: list[str] = []
    for item in raw:
        route = normalize_route(item)
        if route in seen:
            continue
        seen.add(route)
        normalized.append(route)

    return normalized or list(DEFAULT_ROUTES)


def get_active_routes(state: LearningState) -> list[str]:
    """从 state 读取当前应执行的路由（优先 routes，兼容 route）。"""
    routes = state.get("routes")
    if routes:
        return normalize_routes(routes)
    return normalize_routes(None, legacy_route=state.get("route"))


def format_merged_retrieved_context(contexts: dict[str, str]) -> str:
    """将分路由上下文合并为可读字符串（写入 retrieved_context）。"""
    if not contexts:
        return DEFAULT_RETRIEVED_CONTEXT
    blocks: list[str] = []
    for route in ("theory", "practice", "data", "literature"):
        text = (contexts.get(route) or "").strip()
        if not text:
            continue
        label = ROUTE_LABELS.get(route, route)
        blocks.append(f"=== [{label} 知识库] ===\n{text}")
    return "\n\n".join(blocks) if blocks else DEFAULT_RETRIEVED_CONTEXT


# ---------------------------------------------------------------------------
# 图状态
# ---------------------------------------------------------------------------


class LearningState(TypedDict, total=False):
    """
    教育智能体 LangGraph 图状态。

    routes : 当前执行的路由列表（LLM Router 通常为单元素）
    route : 主路由（canonical，如 data_analysis → data）
    route_reason : LLM Router 给出的分类理由
    retrieved_contexts : 分域 RAG 结果，键为 theory / practice / data / literature
    retrieved_context : 合并后的参考文本（便于调试与兼容）
    literature_content : 文献原文（PDF 解析文本，可选显式传入）
    student_reflection : 学生阅读心得（可选显式传入）
    student_id : 学生标识，用于长期记忆 JSON
    session_id : 会话标识，对应 memory/sessions/{session_id}.json
    chat_history : 多轮对话历史（user / assistant 等）
    uploaded_files : 本次提交上传的文件元信息
    memory_context : retrieve_memory_node 格式化的历史评价摘要文本
    evaluation_history : 结构化历史评估记录列表（retrieve_memory 加载 / save_memory 追加）
    research_context : Deep Research 联网摘要（deep_research_node 写入，供评估参考）
    enable_deep_research : 是否启用 Deep Research（默认由环境变量决定）
    """

    student_input: str
    literature_content: str
    student_reflection: str
    student_id: str
    session_id: str
    chat_history: Annotated[list[HistoryTurn], append_history]
    uploaded_files: Annotated[list[UploadedFile], merge_uploaded_files]
    retrieved_context: str
    retrieved_contexts: Annotated[dict[str, str], merge_retrieved_contexts]
    memory_context: str
    evaluation_history: Annotated[list[EvaluationRecord], merge_evaluation_history]
    research_context: str
    enable_deep_research: bool
    memory_retrieve_k: int

    routes: Annotated[list[str], merge_routes]
    route: str
    route_reason: str

    theory_result: TheoryResult | str
    practice_result: PracticeResult
    data_result: DataResult
    literature_result: LiteratureResult
    total_score: float
    score_detail: ScoreDetail
    final_feedback: str
    last_saved_evaluation_id: str
    history_memory: Annotated[list[HistoryTurn], append_history]


# ---------------------------------------------------------------------------
# 节点 Partial State Update
# ---------------------------------------------------------------------------


class SupervisorNodeUpdate(TypedDict, total=False):
    routes: list[str]
    route: str
    route_reason: str


class RetrieveMemoryNodeUpdate(TypedDict, total=False):
    memory_context: str
    evaluation_history: list[EvaluationRecord]


class SaveMemoryNodeUpdate(TypedDict, total=False):
    last_saved_evaluation_id: str
    evaluation_history: list[EvaluationRecord] | EvaluationRecord


class DeepResearchNodeUpdate(TypedDict, total=False):
    research_context: str


class RetrieveContextNodeUpdate(TypedDict, total=False):
    retrieved_context: str
    retrieved_contexts: dict[str, str]


class InputNodeUpdate(TypedDict, total=False):
    student_input: str
    uploaded_files: list[UploadedFile] | UploadedFile


class TheoryNodeUpdate(TypedDict, total=False):
    theory_result: TheoryResult
    history_memory: list[HistoryTurn]


class PracticeNodeUpdate(TypedDict, total=False):
    practice_result: PracticeResult
    history_memory: list[HistoryTurn]


class DataNodeUpdate(TypedDict, total=False):
    data_result: DataResult
    history_memory: list[HistoryTurn]


class LiteratureNodeUpdate(TypedDict, total=False):
    literature_result: LiteratureResult
    history_memory: list[HistoryTurn]


class SynthesisNodeUpdate(TypedDict, total=False):
    final_feedback: str
    history_memory: list[HistoryTurn]


class ScoringNodeUpdate(TypedDict, total=False):
    total_score: float
    score_detail: ScoreDetail


EduAgentState = LearningState
GraphState = LearningState

ROUTE_TO_NODE: dict[str, str] = {
    "theory": "theory_agent",
    "practice": "practice_agent",
    "data": "data_agent",
    "literature": "literature_agent",
}


def create_initial_state(
    student_input: str,
    *,
    uploaded_files: list[UploadedFile] | None = None,
    session_id: str | None = None,
    chat_history: list[HistoryTurn] | None = None,
    retrieved_context: str | None = None,
    routes: list[str] | None = None,
    student_id: str | None = None,
    memory_context: str | None = None,
    evaluation_history: list[EvaluationRecord] | None = None,
    research_context: str | None = None,
    enable_deep_research: bool | None = None,
    memory_retrieve_k: int = 3,
) -> LearningState:
    active_routes = normalize_routes(routes)
    return {
        "student_input": student_input,
        "student_id": (student_id or "").strip(),
        "session_id": (session_id or "").strip(),
        "chat_history": list(chat_history or []),
        "uploaded_files": list(uploaded_files or []),
        "retrieved_context": retrieved_context or DEFAULT_RETRIEVED_CONTEXT,
        "retrieved_contexts": {},
        "memory_context": memory_context or DEFAULT_MEMORY_CONTEXT,
        "evaluation_history": list(evaluation_history or []),
        "research_context": research_context or DEFAULT_RESEARCH_CONTEXT,
        "enable_deep_research": enable_deep_research,
        "memory_retrieve_k": memory_retrieve_k,
        "routes": active_routes,
        "route": active_routes[0],
        "theory_result": dict(DEFAULT_THEORY_RESULT),
        "practice_result": dict(DEFAULT_PRACTICE_RESULT),
        "data_result": dict(DEFAULT_DATA_RESULT),
        "literature_result": dict(DEFAULT_LITERATURE_RESULT),
        "total_score": 0.0,
        "score_detail": dict(DEFAULT_SCORE_DETAIL),
        "last_saved_evaluation_id": "",
        "history_memory": [],
    }


def create_initial_state_from_graph_input(
    student_input: str,
    uploaded_files: list[UploadedFile] | None = None,
) -> LearningState:
    return create_initial_state(
        student_input,
        uploaded_files=uploaded_files,
        retrieved_context=DEFAULT_RETRIEVED_CONTEXT,
    )


__all__ = [
    "DEFAULT_DATA_RESULT",
    "DEFAULT_LITERATURE_RESULT",
    "DEFAULT_PRACTICE_RESULT",
    "DEFAULT_SCORE_DETAIL",
    "DEFAULT_THEORY_RESULT",
    "DEFAULT_EVALUATION_HISTORY",
    "DEFAULT_MEMORY_CONTEXT",
    "DEFAULT_RESEARCH_CONTEXT",
    "DEFAULT_RETRIEVED_CONTEXT",
    "DEFAULT_ROUTES",
    "DEFAULT_CHAT_HISTORY",
    "DEFAULT_UPLOADED_FILES",
    "ROUTE_ALIASES",
    "ROUTE_LABELS",
    "ROUTE_TO_NODE",
    "VALID_ROUTES",
    "DataNodeUpdate",
    "DataResult",
    "DeepResearchNodeUpdate",
    "EduAgentState",
    "EvaluationRecord",
    "GraphState",
    "HistoryTurn",
    "InputNodeUpdate",
    "LearningState",
    "LiteratureNodeUpdate",
    "LiteratureResult",
    "PracticeNodeUpdate",
    "PracticeResult",
    "RetrieveContextNodeUpdate",
    "RetrieveMemoryNodeUpdate",
    "SaveMemoryNodeUpdate",
    "ScoreDetail",
    "ScoreDetailItem",
    "ScoringNodeUpdate",
    "SupervisorNodeUpdate",
    "SynthesisNodeUpdate",
    "TheoryNodeUpdate",
    "TheoryResult",
    "UploadedFile",
    "append_history",
    "create_initial_state",
    "create_initial_state_from_graph_input",
    "format_merged_retrieved_context",
    "get_active_routes",
    "merge_evaluation_history",
    "merge_retrieved_contexts",
    "merge_routes",
    "merge_uploaded_files",
    "normalize_route",
    "normalize_routes",
]
