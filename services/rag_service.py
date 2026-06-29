"""
PBL 参考报告 RAG 服务（从 preview-agent 完整迁移整合）。

功能：
- Embedding：OpenAI-compatible API 或本地 hash fallback
- 索引：JSON 向量索引（rag_index.json）+ ChromaDB 持久化向量库
- 检索：按二级指标硬过滤 + 向量相似度 + 关键词/量规重排
- 入库：参考报告 PDF/DOCX/TXT 拆分与索引重建

数据目录（默认）：<project_root>/data/pbl_rag/
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import shutil
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, TypedDict

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

PBL_RAG_DIR = Path(os.getenv("PBL_RAG_DIR", str(_PROJECT_ROOT / "data" / "pbl_rag")))
REFERENCE_REPORTS_PATH = PBL_RAG_DIR / "reference_reports.json"
RAG_INDEX_PATH = PBL_RAG_DIR / "rag_index.json"
CHROMA_PERSIST_DIR = PBL_RAG_DIR / "chroma"
CHROMA_COLLECTION_NAME = os.getenv("PBL_RAG_CHROMA_COLLECTION", "pbl_reference_fragments")

USE_DB_REFERENCE = os.getenv("USE_DB_REFERENCE", "false").lower() in ("1", "true", "yes")
USE_CHROMA = os.getenv("PBL_RAG_USE_CHROMA", "true").lower() in ("1", "true", "yes")

DEFAULT_LOCAL_EMBEDDING_DIM = int(os.getenv("RAG_LOCAL_EMBEDDING_DIM", "512"))

PBL_STAGES = [
    "问题界定",
    "方案建构",
    "方案实施",
    "反思调节",
    "问题提出",
    "方案新颖性",
    "创新表征",
    "创新表达",
    "证据分析",
    "数据分析",
    "逻辑推演",
    "局限性评价",
]

STAGE_CONCEPTS: Dict[str, List[str]] = {
    "问题界定": [
        "问题界定", "研究问题", "问题定义", "问题边界", "研究边界",
        "自变量", "因变量", "控制变量", "变量", "变量界定", "变量混用",
        "核心假设", "研究假设", "假设", "检验性", "可检验", "可测量",
        "检验指标", "量化指标", "可量化", "量纲", "单位", "数值范围",
        "数值区间", "范围", "物理约束", "约束条件", "边界条件",
        "适用限制", "适用范围", "系统边界", "操作性", "测量指标",
    ],
    "方案建构": [
        "方案建构", "方案设计", "实验方案", "项目方案", "设计方案",
        "项目目标", "实验目标", "研究目标", "理论依据", "操作步骤",
        "实施步骤", "实验步骤", "流程", "操作流程", "技术路线",
        "变量控制", "控制变量", "数据记录", "记录计划", "数据记录计划",
        "误差控制", "误差控制预案", "实施条件", "操作细节", "可行性",
        "可重复性", "器材条件", "器材匹配", "流程完整", "关键步骤",
    ],
    "方案实施": [
        "方案实施", "实施过程", "实验过程", "项目实施", "建模过程",
        "设计过程", "制作过程", "测试过程", "验证过程", "过程记录",
        "实验记录", "关键步骤", "关键条件", "实施步骤", "实施记录",
        "变量控制", "设计约束", "测试结果", "验证结果", "关键结果",
        "现象记录", "条件记录", "评价指标", "预设指标", "目标回应",
        "项目目标", "研究问题", "目标达成", "结果说明",
    ],
    "反思调节": [
        "反思调节", "反思", "问题反思", "总结反思", "改进", "改进方案",
        "优化", "优化方案", "调整", "调节", "存在问题", "主要问题",
        "不足", "不足之处", "局限", "改进方向", "改进环节", "具体改法",
        "怎么改", "可操作", "针对性", "预期效果", "可能效果",
        "增加实验次数", "改进装置", "优化流程", "可行性",
    ],
    "问题提出": [
        "问题提出", "提出问题", "项目问题", "研究问题", "问题来源",
        "研究背景", "项目背景", "切入角度", "新颖角度", "独特视角",
        "理论视角", "跨学科", "跨学科维度", "问题结构", "问题重构",
        "重新框定", "问题内涵", "深度挖掘", "常规思路", "思维定式",
        "主动突破", "自主重构", "常见主题", "直接平移", "新情境",
        "迁移", "生成潜力", "探究价值",
    ],
    "方案新颖性": [
        "方案新颖性", "新颖性", "创新方案", "自主创新", "自主设计",
        "方法创新", "装置创新", "模型创新", "技术路线", "实现方式",
        "关键环节", "创新依据", "独特之处", "常规方案", "已有方案",
        "器材改进", "流程改进", "结构改进", "模型改进", "技术路线改进",
        "主要新意", "创新深度", "独特性", "借鉴", "调整", "组合",
        "替换", "局部创新", "非关键环节", "照搬", "拼凑",
    ],
    "创新表征": [
        "创新表征", "表征", "专业工具", "工具", "MATLAB", "Origin",
        "Python", "Seaborn", "CAD", "复杂可视化", "可视化", "建模",
        "可视化建模", "模型", "图示", "草图", "流程图", "数据图表",
        "图表", "结构图", "关系图", "示意图", "项目思路", "关键关系",
        "问题结构", "方案机制", "成果特点", "关键要素", "关系变化",
        "图表解释", "模型解释", "机制原理", "创新价值", "创新作用",
        "标注", "要素缺失", "关系不准",
    ],
    "创新表达": [
        "创新表达", "创新点", "核心创新点", "核心创新", "主要创新点",
        "创新说明", "常规做法", "已有方案", "方案改进", "改进之处",
        "解决问题", "优化方案", "提升效果", "应用价值", "应用意义",
        "应用场景", "适用条件", "适用范围", "迁移可能", "可迁移性",
        "局限", "成果价值", "成果意义", "改进价值", "核心贡献",
        "贡献", "情境", "实际问题",
    ],
    "证据分析": [
        "证据分析", "证据", "文献", "参考文献", "文献证据", "理论",
        "理论依据", "理论证据", "前人研究", "已有研究", "研究局限",
        "局限性", "矛盾点", "弥补", "改进", "权威性", "可靠性",
        "条件异同", "交叉对比", "权重辨析", "理论引用", "公式",
        "核心公式", "模型", "理论模型", "原始假设", "假设条件",
        "适用边界", "满足程度", "偏离影响", "逻辑关联", "理论前提",
    ],
    "数据分析": [
        "数据分析", "数据", "数据采集", "采集过程", "数据记录",
        "重复测量", "重复实验", "重复性", "误差控制", "质量检查",
        "数据处理", "处理方法", "均值", "平均值", "标准差", "误差分析",
        "拟合", "对比分析", "统计分析", "比较方法", "趋势", "实验趋势",
        "数据规律", "规律描述", "量化对照", "定性对照", "半定量对照",
        "理论预期", "模型预测", "设计目标", "项目目标", "简单计算",
        "直接比较", "表面趋势", "数据结构", "异常数据", "结果判断",
    ],
    "逻辑推演": [
        "逻辑推演", "推理", "推理链条", "逻辑链条", "关键前提",
        "前提", "理论", "数据", "项目证据", "证据", "判断", "结论",
        "可检验判断", "证据一致性", "一致性", "相关", "因果",
        "相关与因果", "假设", "推论", "结论条件", "成立条件",
        "适用范围", "合理解释", "现象解释", "证据趋势", "复杂关系",
        "条件限制", "替代解释", "显性推理", "以偏概全", "循环论证",
        "原理解释",
    ],
    "局限性评价": [
        "局限性评价", "局限性", "局限", "不足", "误差", "误差来源",
        "数据质量", "实验条件", "变量控制", "模型假设", "样本范围",
        "样本量", "结论可靠性", "可靠性", "适用边界", "适用范围",
        "结论可信", "结论可信度", "谨慎解释", "限制条件", "影响结论",
        "主要局限", "系统判断", "结论限制", "不准确", "有误差",
        "可信度", "项目实际",
    ],
}

STAGE_PREFIX_MAP = {
    "问题界定": "problem_definition",
    "方案建构": "plan_construction",
    "方案实施": "plan_implementation",
    "反思调节": "reflection_adjustment",
    "问题提出": "problem_posing",
    "方案新颖性": "plan_novelty",
    "创新表征": "innovation_representation",
    "创新表达": "innovation_expression",
    "证据分析": "evidence_analysis",
    "数据分析": "data_analysis",
    "逻辑推演": "logical_reasoning",
    "局限性评价": "limitation_evaluation",
}


class RagFragment(TypedDict):
    fragment_id: str
    report_name: str
    quality_level: str
    stage_name: str
    text: str
    embedding: List[float]


class RagIndex(TypedDict):
    _meta: Dict[str, Any]
    fragments: List[RagFragment]


# ---------------------------------------------------------------------------
# Embedding（preview-agent rag/semantic.py）
# ---------------------------------------------------------------------------

def _normalize_vector(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm <= 1e-12:
        return vec
    return [x / norm for x in vec]


def _hash_index(token: str, dim: int) -> int:
    digest = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(digest, 16) % dim


def _tokenize_for_local_embedding(text: str) -> List[str]:
    text = text or ""
    chunks = re.findall(r"[\u4e00-\u9fa5]+|[A-Za-z0-9_]+", text)
    tokens: List[str] = []

    for chunk in chunks:
        if re.fullmatch(r"[\u4e00-\u9fa5]+", chunk):
            if len(chunk) <= 2:
                tokens.append(chunk)
            else:
                for n in (2, 3):
                    for i in range(0, len(chunk) - n + 1):
                        tokens.append(chunk[i : i + n])
        else:
            tokens.append(chunk.lower())

    return tokens


def local_hash_embedding(text: str, dim: int = DEFAULT_LOCAL_EMBEDDING_DIM) -> List[float]:
    """本地 char n-gram hashing embedding（无 API Key 时 fallback）。"""
    vec = [0.0] * dim
    tokens = _tokenize_for_local_embedding(text)
    if not tokens:
        return vec

    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1

    for token, count in counts.items():
        idx = _hash_index(token, dim)
        sign = -1.0 if _hash_index("sign::" + token, 2) == 0 else 1.0
        vec[idx] += sign * (1.0 + math.log(count))

    return _normalize_vector(vec)


@lru_cache(maxsize=1)
def _get_openai_embeddings_client():
    api_key = (
        os.getenv("RAG_EMBEDDING_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
    )
    if not api_key:
        return None

    try:
        from langchain_openai import OpenAIEmbeddings
    except Exception:
        return None

    model = os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-small")
    base_url = os.getenv("RAG_EMBEDDING_BASE_URL") or os.getenv("OPENAI_BASE_URL")

    kwargs: Dict[str, Any] = {"model": model, "api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url

    try:
        return OpenAIEmbeddings(**kwargs)
    except Exception:
        return None


def embed_text(text: str) -> List[float]:
    """
    文本向量化：优先 OpenAI-compatible Embeddings API，失败则本地 hash embedding。
    """
    client = _get_openai_embeddings_client()
    if client is not None:
        try:
            return list(client.embed_query(text or ""))
        except Exception as exc:
            logger.warning("OpenAI embedding 失败，回退本地 hash：%s", exc)

    return local_hash_embedding(text or "")


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(n):
        x = float(a[i])
        y = float(b[i])
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 1e-12 or nb <= 1e-12:
        return 0.0
    return dot / math.sqrt(na * nb)


# ---------------------------------------------------------------------------
# ChromaDB 初始化与同步（preview-agent JSON 索引 → Chroma 持久化）
# ---------------------------------------------------------------------------

class ChromaRagStore:
    """PBL 参考片段 ChromaDB 向量库。"""

    def __init__(
        self,
        persist_directory: Path = CHROMA_PERSIST_DIR,
        collection_name: str = CHROMA_COLLECTION_NAME,
    ) -> None:
        import chromadb

        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name

        self._client = chromadb.PersistentClient(path=str(self.persist_directory))
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def collection(self):
        return self._collection

    def count(self) -> int:
        return int(self._collection.count())

    def clear(self) -> None:
        try:
            self._client.delete_collection(self.collection_name)
        except Exception:
            pass
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def sync_from_index(self, index: Dict[str, Any], *, force: bool = False) -> int:
        """
        将 JSON 索引中的 fragments 同步到 ChromaDB。
        若集合已有数据且 force=False，则跳过。
        """
        fragments = list(index.get("fragments", []))
        if not fragments:
            return 0

        if not force and self.count() >= len(fragments):
            return self.count()

        self.clear()

        batch_size = 100
        synced = 0

        for start in range(0, len(fragments), batch_size):
            batch = fragments[start : start + batch_size]
            ids: List[str] = []
            documents: List[str] = []
            embeddings: List[List[float]] = []
            metadatas: List[Dict[str, Any]] = []

            for fragment in batch:
                fragment_id = str(fragment.get("fragment_id", "")).strip()
                text = str(fragment.get("text", "")).strip()
                if not fragment_id or not text:
                    continue

                emb = fragment.get("embedding") or embed_text(text)
                ids.append(fragment_id)
                documents.append(text)
                embeddings.append([float(x) for x in emb])
                metadatas.append(
                    {
                        "report_name": str(fragment.get("report_name", "")),
                        "quality_level": str(fragment.get("quality_level", "")),
                        "stage_name": str(fragment.get("stage_name", "")),
                    }
                )

            if ids:
                self._collection.upsert(
                    ids=ids,
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )
                synced += len(ids)

        return synced

    def vector_search(
        self,
        query_text: str,
        *,
        top_n: int = 30,
        target_stage: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if self.count() == 0:
            return []

        query_embedding = embed_text(query_text)
        where: Optional[Dict[str, Any]] = None
        if target_stage:
            where = {"stage_name": target_stage}

        try:
            raw = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_n, self.count()),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.warning("ChromaDB 检索失败（stage=%s）：%s", target_stage, exc)
            if target_stage:
                raw = self._collection.query(
                    query_embeddings=[query_embedding],
                    n_results=min(top_n, self.count()),
                    include=["documents", "metadatas", "distances"],
                )
            else:
                return []

        results: List[Dict[str, Any]] = []
        ids = (raw.get("ids") or [[]])[0]
        docs = (raw.get("documents") or [[]])[0]
        metas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]

        for i, fragment_id in enumerate(ids):
            meta = metas[i] if i < len(metas) else {}
            text = docs[i] if i < len(docs) else ""
            distance = distances[i] if i < len(distances) else 1.0
            vector_score = max(0.0, 1.0 - float(distance))

            results.append(
                {
                    "fragment_id": fragment_id,
                    "report_name": meta.get("report_name", ""),
                    "quality_level": meta.get("quality_level", ""),
                    "stage_name": meta.get("stage_name", ""),
                    "text": text,
                    "vector_score": vector_score,
                }
            )

        if target_stage:
            results = [r for r in results if r.get("stage_name") == target_stage]

        results.sort(key=lambda x: x.get("vector_score", 0.0), reverse=True)
        return results[:top_n]


_chroma_store: Optional["ChromaRagStore"] = None
_chroma_disabled = False


def _quarantine_chroma_dir() -> None:
    """隔离损坏或不可用的 Chroma 持久化目录，便于下次重建。"""
    if not CHROMA_PERSIST_DIR.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup = CHROMA_PERSIST_DIR.with_name(f"chroma.bad.{stamp}")
    try:
        shutil.move(str(CHROMA_PERSIST_DIR), str(backup))
        logger.warning("已隔离 ChromaDB 目录 → %s", backup.name)
    except Exception as exc:
        logger.warning("隔离 ChromaDB 目录失败：%s", exc)


def try_get_chroma_store(*, retry_after_quarantine: bool = True) -> Optional["ChromaRagStore"]:
    """
    安全获取 Chroma 实例；失败时返回 None 并降级 JSON 检索。
    捕获 BaseException（含 PyO3 PanicException），避免拖垮整次评价。
    """
    global _chroma_store, _chroma_disabled

    if not USE_CHROMA or _chroma_disabled:
        return None
    if _chroma_store is not None:
        return _chroma_store

    def _init() -> "ChromaRagStore":
        return ChromaRagStore()

    try:
        _chroma_store = _init()
        return _chroma_store
    except BaseException as exc:
        logger.warning("ChromaDB 初始化失败：%s", exc)
        if retry_after_quarantine:
            _quarantine_chroma_dir()
            try:
                _chroma_store = _init()
                logger.info("ChromaDB 隔离旧数据后初始化成功")
                return _chroma_store
            except BaseException as exc2:
                logger.warning("ChromaDB 重试仍失败，降级 JSON RAG：%s", exc2)
        _chroma_disabled = True
        _chroma_store = None
        return None


def get_chroma_store() -> "ChromaRagStore":
    store = try_get_chroma_store()
    if store is None:
        raise RuntimeError("ChromaDB 不可用，已降级 JSON RAG")
    return store


def _rag_backend_name() -> str:
    store = try_get_chroma_store(retry_after_quarantine=False)
    if store is None:
        return "json"
    try:
        return "chroma" if store.count() > 0 else "json"
    except BaseException:
        return "json"


# ---------------------------------------------------------------------------
# 文档读取（preview-agent rag/document_reader.py）
# ---------------------------------------------------------------------------

def read_txt(file_path: str | Path) -> str:
    return Path(file_path).read_text(encoding="utf-8").strip()


def read_docx(file_path: str | Path) -> str:
    from docx import Document

    doc = Document(str(file_path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs).strip()


def read_pdf_text(file_path: str | Path) -> str:
    import fitz

    doc = fitz.open(str(file_path))
    texts: List[str] = []
    for page_index, page in enumerate(doc):
        text = page.get_text("text")
        if text and text.strip():
            texts.append(f"\n--- 第 {page_index + 1} 页文本 ---\n{text.strip()}")
    doc.close()
    return "\n".join(texts).strip()


def read_document(file_path: str | Path) -> str:
    ext = Path(file_path).suffix.lower()
    if ext == ".txt":
        return read_txt(file_path)
    if ext == ".docx":
        return read_docx(file_path)
    if ext == ".pdf":
        return read_pdf_text(file_path)
    raise ValueError(f"暂不支持的文件类型：{ext}。当前支持 .pdf / .docx / .txt")


# ---------------------------------------------------------------------------
# 索引构建（preview-agent rag/builder.py）
# ---------------------------------------------------------------------------

def build_rag_index(
    reference_json_path: Path = REFERENCE_REPORTS_PATH,
    output_index_path: Path = RAG_INDEX_PATH,
    *,
    sync_chroma: bool = USE_CHROMA,
) -> Dict[str, Any]:
    PBL_RAG_DIR.mkdir(parents=True, exist_ok=True)

    with open(reference_json_path, "r", encoding="utf-8") as f:
        reports = json.load(f)

    fragments: List[Dict[str, Any]] = []

    for report in reports:
        report_name = str(report.get("report_name", "")).strip()
        quality_level = str(report.get("quality_level", "")).strip()

        for stage in report.get("stages", []):
            stage_name = str(stage.get("stage_name", "")).strip()

            for fragment in stage.get("fragments", []):
                fragment_id = str(fragment.get("fragment_id", "")).strip()
                text = str(fragment.get("text", "")).strip()
                if not fragment_id or not text:
                    continue

                fragments.append(
                    {
                        "fragment_id": fragment_id,
                        "report_name": report_name,
                        "quality_level": quality_level,
                        "stage_name": stage_name,
                        "text": text,
                        "embedding": embed_text(text),
                    }
                )

    index: Dict[str, Any] = {
        "_meta": {
            "schema": "rag_v1",
            "description": "PBL reference fragments with embeddings",
            "fragment_count": len(fragments),
            "source": "file",
        },
        "fragments": fragments,
    }

    output_index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    if sync_chroma:
        try:
            store = try_get_chroma_store()
            if store is not None:
                synced = store.sync_from_index(index, force=True)
                index["_meta"]["chroma_synced"] = synced
                logger.info("ChromaDB 已同步 %d 条参考片段", synced)
        except BaseException as exc:
            logger.warning("ChromaDB 同步失败：%s", exc)

    return index


def _read_cached_index_version(index_path: Path = RAG_INDEX_PATH) -> Optional[str]:
    if not index_path.exists():
        return None
    try:
        with index_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("_meta", {}).get("version")
    except Exception:
        return None


def _try_load_index_from_db() -> Optional[Dict[str, Any]]:
    """可选：从完整项目的 db.session 导出参考语料（preview-agent db_loader）。"""
    if not USE_DB_REFERENCE:
        return None
    try:
        from db.session import get_session
        from db.repositories.rag import RagRepository

        with get_session() as session:
            repo = RagRepository(session)
            repo.write_reference_json_cache(REFERENCE_REPORTS_PATH)
            db_version = repo.compute_index_version()

        index = build_rag_index(sync_chroma=USE_CHROMA)
        if db_version:
            index["_meta"]["version"] = db_version
            index["_meta"]["source"] = "db"
            RAG_INDEX_PATH.write_text(
                json.dumps(index, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return index
    except Exception as exc:
        logger.debug("DB 参考语料加载不可用：%s", exc)
        return None


def load_rag_index(
    reference_json_path: Path = REFERENCE_REPORTS_PATH,
    index_path: Path = RAG_INDEX_PATH,
    *,
    sync_chroma: bool = USE_CHROMA,
) -> Dict[str, Any]:
    db_index = _try_load_index_from_db()
    if db_index is not None:
        return db_index

    if not index_path.exists():
        if not reference_json_path.exists():
            return {"_meta": {"schema": "rag_v1", "fragment_count": 0}, "fragments": []}
        return build_rag_index(reference_json_path, index_path, sync_chroma=sync_chroma)

    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    if sync_chroma:
        try:
            store = try_get_chroma_store()
            if store is not None and store.count() == 0 and index.get("fragments"):
                store.sync_from_index(index, force=True)
        except BaseException as exc:
            logger.warning("ChromaDB 懒同步失败：%s", exc)

    return index


# ---------------------------------------------------------------------------
# 检索辅助（preview-agent rag/retriever.py）
# ---------------------------------------------------------------------------

def extract_chinese_terms(text: str, min_len: int = 2, max_terms: int = 120) -> List[str]:
    text = text or ""
    raw_terms = re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{%d,}" % min_len, text)
    stop_terms = {
        "学生", "报告", "当前", "评分", "维度", "内容", "进行", "说明", "分析",
        "评价", "根据", "以下", "可以", "需要", "一个", "这个", "通过", "以及",
        "没有", "较为", "比较", "相关", "参考", "片段", "优质", "普通",
    }
    terms: List[str] = []
    seen: set[str] = set()
    for term in raw_terms:
        term = term.strip()
        if not term or term in stop_terms or len(term) < min_len:
            continue
        if term not in seen:
            terms.append(term)
            seen.add(term)
        if len(terms) >= max_terms:
            break
    return terms


def keyword_overlap_score_without_stage(
    query_text: str,
    fragment_text: str,
    dimension_name: str,
    rubric: str,
    fragment_quality: str,
    fragment_stage_name: str = "",
) -> int:
    score = 0
    query_text = query_text or ""
    fragment_text = fragment_text or ""
    dimension_name = dimension_name or ""
    rubric = rubric or ""
    fragment_stage_name = fragment_stage_name or ""

    if dimension_name and dimension_name in fragment_text:
        score += 8
    if dimension_name and dimension_name == fragment_stage_name:
        score += 6

    rubric_keywords = [
        "问题", "界定", "证据", "数据", "逻辑", "推理", "演绎", "反思", "调节",
        "改进", "变量", "结论", "分析", "论证", "假设", "实验", "模型", "建模",
        "可靠性", "相关性", "充分", "趋势", "误差", "异常值", "局限", "方法",
        "解释", "支持", "控制变量", "自变量", "因变量", "平均值", "图表", "现象",
        "原因", "创新",
    ]
    for kw in rubric_keywords:
        in_rubric = kw in rubric
        in_query = kw in query_text
        in_fragment = kw in fragment_text
        if in_rubric and in_fragment:
            score += 2
        if in_query and in_fragment:
            score += 3
        if in_rubric and in_query and in_fragment:
            score += 2

    for concept in STAGE_CONCEPTS.get(fragment_stage_name, []):
        in_query = concept in query_text
        in_fragment = concept in fragment_text
        in_rubric = concept in rubric
        if in_query and in_fragment:
            score += 5
        elif in_fragment:
            score += 1
        if in_rubric and in_fragment:
            score += 2

    candidate_terms: List[str] = []
    candidate_terms.extend(extract_chinese_terms(dimension_name, min_len=2, max_terms=20))
    candidate_terms.extend(extract_chinese_terms(rubric, min_len=2, max_terms=80))
    candidate_terms.extend(extract_chinese_terms(query_text, min_len=2, max_terms=120))

    for term in dict.fromkeys(candidate_terms):
        if term in fragment_text:
            score += 2 if len(term) >= 4 else 1

    if fragment_quality == "优质":
        score += 2
    elif fragment_quality == "普通":
        score += 1

    return score


def normalize_score(value: float, cap: float = 70.0) -> float:
    if value <= 0:
        return 0.0
    return min(1.0, value / cap)


def get_fragments(index: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(index.get("fragments", []))


def vector_search_json(
    index: Dict[str, Any],
    query_text: str,
    top_n: int = 30,
    target_stage: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """基于 JSON 索引的向量检索（preview-agent 原始实现）。"""
    query_embedding = embed_text(query_text)
    results: List[Dict[str, Any]] = []

    for fragment in get_fragments(index):
        if target_stage and fragment.get("stage_name") != target_stage:
            continue

        emb = fragment.get("embedding") or embed_text(fragment.get("text", ""))
        sim = cosine_similarity(query_embedding, emb)
        item = dict(fragment)
        item["vector_score"] = sim
        results.append(item)

    results.sort(key=lambda x: x.get("vector_score", 0.0), reverse=True)
    return results[:top_n]


def vector_search(
    index: Dict[str, Any],
    query_text: str,
    top_n: int = 30,
    target_stage: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    向量检索：优先 ChromaDB，失败或未启用时回退 JSON 索引。
    """
    if USE_CHROMA:
        try:
            store = try_get_chroma_store()
            if store is not None and store.count() > 0:
                chroma_results = store.vector_search(
                    query_text,
                    top_n=top_n,
                    target_stage=target_stage,
                )
                if chroma_results:
                    return chroma_results
        except BaseException as exc:
            logger.warning("ChromaDB vector_search 失败，回退 JSON：%s", exc)

    return vector_search_json(index, query_text, top_n, target_stage)


def rerank_fragments(
    fragments: List[Dict[str, Any]],
    report_context: str,
    dimension_name: str,
    rubric: str,
) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []

    for item in fragments:
        text = item.get("text", "")
        quality = item.get("quality_level", "")
        stage = item.get("stage_name", "")
        vector_score = float(item.get("vector_score", 0.0))

        keyword_score_raw = keyword_overlap_score_without_stage(
            query_text=report_context,
            fragment_text=text,
            dimension_name=dimension_name,
            rubric=rubric,
            fragment_quality=quality,
            fragment_stage_name=stage,
        )
        keyword_score = normalize_score(keyword_score_raw)
        quality_score = 1.0 if quality == "优质" else 0.75 if quality == "普通" else 0.5

        final_score = 0.65 * vector_score + 0.30 * keyword_score + 0.05 * quality_score

        enriched = dict(item)
        enriched.update(
            {
                "score": round(final_score * 100, 4),
                "vector_score": round(vector_score, 4),
                "keyword_score": round(keyword_score_raw, 4),
            }
        )
        ranked.append(enriched)

    ranked.sort(key=lambda x: x.get("score", 0), reverse=True)
    return ranked


def select_balanced_fragments(scored_fragments: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    if top_k <= 0:
        return []

    scored_fragments = sorted(scored_fragments, key=lambda x: x.get("score", 0), reverse=True)
    excellent = [item for item in scored_fragments if item.get("quality_level") == "优质"]
    normal = [item for item in scored_fragments if item.get("quality_level") == "普通"]

    selected: List[Dict[str, Any]] = []
    excellent_quota = max(1, top_k // 2)
    normal_quota = max(1, top_k // 3)
    selected.extend(excellent[:excellent_quota])
    selected.extend(normal[:normal_quota])

    existing_ids = {item.get("fragment_id") for item in selected}
    for item in scored_fragments:
        if len(selected) >= top_k:
            break
        fragment_id = item.get("fragment_id")
        if fragment_id not in existing_ids:
            selected.append(item)
            existing_ids.add(fragment_id)

    return selected[:top_k]


def format_rag_context(selected_fragments: List[Dict[str, Any]]) -> str:
    if not selected_fragments:
        return ""

    blocks: List[str] = []
    for i, item in enumerate(selected_fragments, start=1):
        blocks.append(
            f"""
【RAG参考片段 {i}】
来源报告：{item.get("report_name", "")}
质量等级：{item.get("quality_level", "")}
项目化学习阶段：{item.get("stage_name", "")}
综合分数：{item.get("score", 0)}
向量相似度：{item.get("vector_score", 0)}
关键词/量规分数：{item.get("keyword_score", 0)}
原文片段：
{item.get("text", "")}
""".strip()
        )

    return "\n\n".join(blocks)


def retrieve_rag_context_auto(
    report_context: str,
    dimension_name: str,
    rubric: str,
    top_k: int = 8,
    reference_json_path: Path = REFERENCE_REPORTS_PATH,
    index_path: Path = RAG_INDEX_PATH,
) -> Tuple[str, Dict[str, Any]]:
    """
    自动检索当前评分维度对应的 RAG 参考片段（preview-agent 主检索入口）。
    """
    report_context = report_context or ""
    dimension_name = dimension_name or ""
    rubric = rubric or ""

    query_text = f"评分维度：{dimension_name}\n评分量规：{rubric}\n学生报告：{report_context}"

    index = load_rag_index(reference_json_path=reference_json_path, index_path=index_path)

    vector_results = vector_search(
        index,
        query_text=query_text,
        top_n=max(30, top_k * 5),
        target_stage=dimension_name,
    )

    fallback_used = False
    if not vector_results:
        fallback_used = True
        vector_results = vector_search(
            index,
            query_text=query_text,
            top_n=max(30, top_k * 5),
            target_stage=None,
        )

    ranked = rerank_fragments(
        fragments=vector_results,
        report_context=report_context,
        dimension_name=dimension_name,
        rubric=rubric,
    )

    if not fallback_used:
        ranked = [item for item in ranked if item.get("stage_name") == dimension_name]

    selected = select_balanced_fragments(ranked, top_k=top_k)
    context = format_rag_context(selected)

    debug = {
        "mode": "rag_auto_dimension_filtered",
        "backend": _rag_backend_name(),
        "schema": index.get("_meta", {}).get("schema", "unknown"),
        "dimension_name": dimension_name,
        "target_stage": dimension_name,
        "top_k": top_k,
        "fallback_used": fallback_used,
        "candidate_fragment_count": len(vector_results),
        "retrieved_count": len(selected),
        "selected_stage_names": [item.get("stage_name", "") for item in selected],
        "selected_fragments": selected,
    }

    return context, debug


def retrieve_rag_context(
    report_context: str,
    target_stage: str,
    top_k: int = 8,
    reference_json_path: Path = REFERENCE_REPORTS_PATH,
    index_path: Path = RAG_INDEX_PATH,
) -> Tuple[str, Dict[str, Any]]:
    if target_stage not in PBL_STAGES:
        raise ValueError(f"target_stage 必须是以下之一：{PBL_STAGES}")

    query_text = f"阶段：{target_stage}\n学生报告：{report_context or ''}"
    index = load_rag_index(reference_json_path=reference_json_path, index_path=index_path)

    vector_results = vector_search(
        index,
        query_text=query_text,
        top_n=max(30, top_k * 5),
        target_stage=target_stage,
    )
    ranked = rerank_fragments(
        fragments=vector_results,
        report_context=report_context or "",
        dimension_name=target_stage,
        rubric="",
    )
    selected = select_balanced_fragments(ranked, top_k=top_k)
    context = format_rag_context(selected)

    debug = {
        "mode": "rag_target_stage",
        "backend": _rag_backend_name(),
        "schema": index.get("_meta", {}).get("schema", "unknown"),
        "target_stage": target_stage,
        "top_k": top_k,
        "candidate_fragment_count": len(vector_results),
        "retrieved_count": len(selected),
        "selected_fragments": selected,
    }
    return context, debug


# ---------------------------------------------------------------------------
# 参考报告入库（preview-agent rag/ingest_reference.py，LLM 懒加载）
# ---------------------------------------------------------------------------

def _get_ingest_llm():
    from langchain_openai import ChatOpenAI

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("入库需要 OPENAI_API_KEY 或 DEEPSEEK_API_KEY")

    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.getenv("OPENAI_MODEL") or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

    if "deepseek.com" in base_url and not base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"

    return ChatOpenAI(model=model, api_key=api_key, base_url=base_url, temperature=0.2)


def _clean_json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text.replace("```json", "", 1).strip()
    if text.startswith("```"):
        text = text.replace("```", "", 1).strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


def _safe_json_loads(text: str) -> Dict[str, Any]:
    text = _clean_json_text(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group(0))
    raise ValueError(f"无法解析模型输出为 JSON：\n{text[:500]}")


def _build_stage_split_prompt(report_name: str, quality_level: str, full_text: str) -> str:
    stages_json = ",\n".join(f'"{s}"' for s in PBL_STAGES)
    return f"""
你是项目化学习报告结构化整理助手。把参考报告原文按 12 个二级指标维度拆分为参考片段。

报告名称：{report_name}
质量等级：{quality_level}

12 个维度固定为：{stages_json}

要求：只抽取原文、不改写；每阶段可合并连续段落；无内容则 fragments 为空数组；输出合法 JSON。

格式：
{{
  "report_name": "{report_name}",
  "quality_level": "{quality_level}",
  "stages": [{{"stage_name": "问题提出", "fragments": [{{"fragment_id": "auto_001", "text": "原文"}}]}}]
}}

报告原文：
{full_text}
""".strip()


def _normalize_fragment_ids(report: Dict[str, Any]) -> Dict[str, Any]:
    report_name = report["report_name"]
    quality_level = report["quality_level"]
    prefix = "excellent" if quality_level == "优质" else "normal" if quality_level == "普通" else "reference"
    safe_report_name = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5]+", "_", report_name)

    for stage in report.get("stages", []):
        stage_name = stage.get("stage_name", "")
        stage_prefix = STAGE_PREFIX_MAP.get(stage_name, "stage")
        for index, fragment in enumerate(stage.get("fragments", []), start=1):
            fragment["fragment_id"] = f"{prefix}_{safe_report_name}_{stage_prefix}_{index:03d}"

    return report


def _validate_report_structure(report: Dict[str, Any]) -> Dict[str, Any]:
    existing = {stage.get("stage_name"): stage for stage in report.get("stages", [])}
    normalized_stages = []

    for stage_name in PBL_STAGES:
        if stage_name in existing:
            stage = existing[stage_name]
            cleaned_fragments = []
            for item in stage.get("fragments", []):
                text = str(item.get("text", "")).strip()
                fragment_id = str(item.get("fragment_id", "")).strip()
                if text:
                    cleaned_fragments.append({"fragment_id": fragment_id, "text": text})
            normalized_stages.append({"stage_name": stage_name, "fragments": cleaned_fragments})
        else:
            normalized_stages.append({"stage_name": stage_name, "fragments": []})

    report["stages"] = normalized_stages
    return report


def load_reference_reports(path: Path = REFERENCE_REPORTS_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_reference_reports(reports: List[Dict[str, Any]], path: Path = REFERENCE_REPORTS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(reports, f, ensure_ascii=False, indent=2)


def upsert_reference_report(new_report: Dict[str, Any], path: Path = REFERENCE_REPORTS_PATH) -> None:
    reports = load_reference_reports(path)
    updated: List[Dict[str, Any]] = []
    found = False
    for report in reports:
        if report.get("report_name") == new_report.get("report_name"):
            updated.append(new_report)
            found = True
        else:
            updated.append(report)
    if not found:
        updated.append(new_report)
    save_reference_reports(updated, path)


def split_report_into_stages(report_name: str, quality_level: str, full_text: str) -> Dict[str, Any]:
    llm = _get_ingest_llm()
    prompt = _build_stage_split_prompt(report_name, quality_level, full_text)
    response = llm.invoke(prompt)
    content = response.content if hasattr(response, "content") else str(response)
    parsed = _safe_json_loads(content)
    parsed["report_name"] = report_name
    parsed["quality_level"] = quality_level
    parsed = _validate_report_structure(parsed)
    parsed = _normalize_fragment_ids(parsed)
    return parsed


def ingest_reference_report(
    file_path: str | Path,
    report_name: str,
    quality_level: str,
    *,
    rebuild_index: bool = True,
) -> Dict[str, Any]:
    if quality_level not in ["优质", "普通"]:
        raise ValueError("quality_level 只能是：优质 或 普通")

    full_text = read_document(file_path)
    if not full_text.strip():
        raise ValueError("未能从文件中提取到文本内容。")

    structured_report = split_report_into_stages(report_name, quality_level, full_text)
    upsert_reference_report(structured_report)

    if rebuild_index:
        build_rag_index(sync_chroma=USE_CHROMA)

    return structured_report


# ---------------------------------------------------------------------------
# 高层服务类
# ---------------------------------------------------------------------------

class RagService:
    """PBL RAG 统一服务入口。"""

    def __init__(
        self,
        *,
        data_dir: Path = PBL_RAG_DIR,
        use_chroma: bool = USE_CHROMA,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.reference_reports_path = self.data_dir / "reference_reports.json"
        self.index_path = self.data_dir / "rag_index.json"
        self.chroma_dir = self.data_dir / "chroma"
        self.use_chroma = use_chroma

    def embed(self, text: str) -> List[float]:
        return embed_text(text)

    def get_chroma_store(self) -> ChromaRagStore:
        return ChromaRagStore(self.chroma_dir, CHROMA_COLLECTION_NAME)

    def load_index(self) -> Dict[str, Any]:
        return load_rag_index(self.reference_reports_path, self.index_path)

    def build_index(self, *, force: bool = False) -> Dict[str, Any]:
        if force or not self.index_path.exists():
            return build_rag_index(self.reference_reports_path, self.index_path, sync_chroma=self.use_chroma)
        return self.load_index()

    def retrieve(
        self,
        report_context: str,
        dimension_name: str,
        rubric: str = "",
        top_k: int = 8,
    ) -> Tuple[str, Dict[str, Any]]:
        return retrieve_rag_context_auto(
            report_context=report_context,
            dimension_name=dimension_name,
            rubric=rubric,
            top_k=top_k,
            reference_json_path=self.reference_reports_path,
            index_path=self.index_path,
        )

    def ingest(
        self,
        file_path: str | Path,
        report_name: str,
        quality_level: str,
        *,
        rebuild_index: bool = True,
    ) -> Dict[str, Any]:
        return ingest_reference_report(
            file_path=file_path,
            report_name=report_name,
            quality_level=quality_level,
            rebuild_index=rebuild_index,
        )


# 模块级默认实例
_default_service: Optional[RagService] = None


def get_rag_service() -> RagService:
    global _default_service
    if _default_service is None:
        _default_service = RagService()
    return _default_service


__all__ = [
    "CHROMA_COLLECTION_NAME",
    "CHROMA_PERSIST_DIR",
    "ChromaRagStore",
    "PBL_RAG_DIR",
    "PBL_STAGES",
    "RAG_INDEX_PATH",
    "REFERENCE_REPORTS_PATH",
    "RagService",
    "build_rag_index",
    "cosine_similarity",
    "embed_text",
    "format_rag_context",
    "get_chroma_store",
    "try_get_chroma_store",
    "get_rag_service",
    "ingest_reference_report",
    "load_rag_index",
    "load_reference_reports",
    "read_document",
    "retrieve_rag_context",
    "retrieve_rag_context_auto",
    "vector_search",
]
