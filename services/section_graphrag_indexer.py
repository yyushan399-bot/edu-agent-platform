import json
import os
import re
from typing import Dict, List

from dotenv import load_dotenv
from neo4j import GraphDatabase

from agents.group_project.pbl_config import DEEPSEEK_BASE_URL, DEFAULT_MODEL
from agents.section_report.section_config import (
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    SECTION_NAMES,
)

load_dotenv()

# pip install neo4j python-docx PyPDF2 openai

LLM_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_BASE_URL = os.getenv("OPENAI_BASE_URL", DEEPSEEK_BASE_URL)
LLM_MODEL = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)

# 报告文件配置：[(文件路径, 报告名称, 整体质量标签), ...]
# 通过环境变量 SECTION_INDEX_REPORTS 传入 JSON，例如：
# [{"path":"reports/a.docx","name":"优质报告1","quality":"exemplar"}]
REPORTS_CONFIG: List[tuple[str, str, str]] = []


def _load_reports_config() -> List[tuple[str, str, str]]:
    raw = os.getenv("SECTION_INDEX_REPORTS", "").strip()
    if not raw:
        return []
    items = json.loads(raw)
    return [(item["path"], item["name"], item["quality"]) for item in items]

SECTION_KEYWORDS = list(SECTION_NAMES)

from data.section_rag.rubrics import RUBRIC_BY_CRITERION
from data.section_rag.section_weights import SECTION_CRITERIA_MAP, SECTION_CRITERIA_WEIGHTS


# ==================== 文件读取 / 章节切分 ====================
from utils.section_parser import (
    read_docx_paragraphs,
    split_report_paragraphs,
    split_report_text,
)


def read_pdf(file_path: str) -> str:
    """读取 .pdf 文件"""
    import PyPDF2
    reader = PyPDF2.PdfReader(file_path)
    texts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            texts.append(text)
    return "\n".join(texts)


def read_txt(file_path: str) -> str:
    """读取 .txt 文件"""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def split_by_sections(text_or_paragraphs, file_path: str = "") -> List[Dict[str, str]]:
    """兼容旧接口：返回 [{section, content}, ...]。"""
    if isinstance(text_or_paragraphs, list):
        parsed = split_report_paragraphs(text_or_paragraphs, file_path=file_path)
    else:
        parsed = split_report_text(str(text_or_paragraphs), file_path=file_path)
    for warning in parsed.warnings:
        print(f"  [警告] {warning}")
    return [{"section": chunk.section_name, "content": chunk.text} for chunk in parsed.sections]


# ==================== LLM Prompt 构建 ====================
def build_llm_prompt(chunk_content: str, section_name: str, quality_tag: str) -> str:
    """
    构建 LLM Prompt，用于自动提取 EXEMPLIFIES 关系。
    只传入该章节相关的指标，减少 Token 消耗并提高准确率。
    """
    relevant_criteria = SECTION_CRITERIA_MAP.get(section_name, [])

    # 拼接相关量规文本
    rubric_parts = []
    for criterion_name in relevant_criteria:
        parent_dim = None
        for dim, criteria in {
            "问题解决能力": ["问题界定", "方案建构", "方案实施", "反思调节"],
            "创造性思维": ["问题提出", "方案新颖性", "创新表征", "创新表达"],
            "批判性思维": ["证据分析", "数据分析", "逻辑推演", "局限性评价"],
        }.items():
            if criterion_name in criteria:
                parent_dim = dim
                break

        rubric_parts.append(f"\n【{parent_dim} — {criterion_name}】")
        scores = RUBRIC_BY_CRITERION.get(criterion_name, {})
        for score in sorted(scores.keys(), reverse=True):
            rubric_parts.append(f"{score}分：{scores[score]}")

    rubric_text = "\n".join(rubric_parts)

    prompt = f"""你是一名 STEM 教育评估专家，精通项目化学习研究报告的评分量规分析。

你的任务：根据以下评分量规，分析给定报告片段最符合哪些二级指标的哪个分值描述（1-5分）。

## 相关评分量规（仅列出该章节可能被评价的指标）
{rubric_text}

## 待分析片段
- 所属章节：{section_name}
- 报告整体质量等级：{quality_tag}
- 片段内容（前3000字）：
{chunk_content[:3000]}

## 任务要求
1. 仔细阅读量规的每个二级指标的1-5分描述。
2. 判断该片段在哪些二级指标上达到了什么分值。一个片段可能对应多个指标。
3. 只返回该片段**明显体现**出的指标，不要勉强匹配。
4. 每个判断必须给出理由，并**引用原文中的具体句子**作为证据。
5. 返回严格的 JSON 格式，不要有任何额外文字（包括 markdown 代码块标记）。

## 输出格式
{{"exemplifies": [{{"criterion": "证据分析", "score": 5, "reason": "片段中'...'体现了..."}}]}}

注意：
- criterion 必须是以下之一：{', '.join(relevant_criteria)}
- score 必须是 1-5 的整数
- 如果没有明显体现任何指标，返回空数组：{{"exemplifies": []}}
"""
    return prompt


# ==================== LLM 调用 ====================
def call_llm(prompt: str) -> Dict:
    """
    调用 LLM API。使用 OpenAI 兼容接口。
    返回解析后的 JSON 字典。
    """
    import openai
    client = openai.OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": "你是一名严谨的 STEM 教育评估专家，只输出纯 JSON 字符串，不输出任何解释性文字、markdown 标记或代码块。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=3000,
    )

    content = response.choices[0].message.content.strip()

    # 清理可能的 markdown 代码块
    content = re.sub(r"^```json\s*", "", content)
    content = re.sub(r"^```\s*", "", content)
    content = re.sub(r"```\s*$", "", content)
    content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"    [警告] JSON 解析失败: {e}")
        print(f"    原始内容: {content[:200]}...")
        return {"exemplifies": []}


# ==================== Neo4j 写入 ====================
class GraphRAGIndexer:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def create_chunk(self, report_name: str, section_name: str, content: str,
                     quality_tag: str, exemplifies: List[Dict]):
        """
        创建 ReportChunk 节点，并建立 BELONGS_TO 和 EXEMPLIFIES 关系。
        """
        with self.driver.session() as session:
            # 1. 创建 ReportChunk
            result = session.run("""
                CREATE (chunk:ReportChunk {
                    content: $content,
                    source_report: $report_name,
                    source_section: $section_name,
                    quality_tag: $quality_tag,
                    created_at: datetime()
                })
                RETURN id(chunk) AS chunk_id
            """, content=content, report_name=report_name,
                 section_name=section_name, quality_tag=quality_tag)

            chunk_id = result.single()["chunk_id"]

            # 2. 建立 BELONGS_TO 关系
            session.run("""
                MATCH (chunk:ReportChunk), (s:ReportSection {name: $section_name})
                WHERE id(chunk) = $chunk_id
                CREATE (chunk)-[:BELONGS_TO]->(s)
            """, chunk_id=chunk_id, section_name=section_name)

            # 3. 建立 EXEMPLIFIES 关系（核心）
            valid_count = 0
            for ex in exemplifies:
                criterion = ex.get("criterion")
                score = ex.get("score")
                reason = ex.get("reason", "")

                if not criterion or not score:
                    continue

                # 检查 ScoreDescriptor 是否存在
                check_result = session.run("""
                    MATCH (sd:ScoreDescriptor {criterion: $criterion, score: $score})
                    RETURN sd IS NOT NULL AS exists
                """, criterion=criterion, score=score)

                if check_result.single()["exists"]:
                    session.run("""
                        MATCH (chunk:ReportChunk), (sd:ScoreDescriptor {
                            criterion: $criterion,
                            score: $score
                        })
                        WHERE id(chunk) = $chunk_id
                        CREATE (chunk)-[:EXEMPLIFIES {reason: $reason}]->(sd)
                    """, chunk_id=chunk_id, criterion=criterion,
                         score=score, reason=reason)
                    valid_count += 1
                else:
                    print(f"    [跳过] 无效指标或分值: {criterion}/{score}")

            print(f"    已写入 chunk_id={chunk_id}, 建立 {valid_count} 个 EXEMPLIFIES 关系")

    def verify_graph(self):
        """验证并打印图谱统计信息"""
        with self.driver.session() as session:
            print("\n=== 节点统计 ===")
            result = session.run("""
                MATCH (n)
                RETURN labels(n)[0] AS label, count(n) AS cnt
                ORDER BY label
            """)
            for record in result:
                print(f"  {record['label']}: {record['cnt']}")

            print("\n=== 关系统计 ===")
            result = session.run("""
                MATCH ()-[r]->()
                RETURN type(r) AS rel_type, count(r) AS cnt
                ORDER BY rel_type
            """)
            for record in result:
                print(f"  {record['rel_type']}: {record['cnt']}")

            print("\n=== ReportChunk 详情 ===")
            result = session.run("""
                MATCH (chunk:ReportChunk)-[:BELONGS_TO]->(s:ReportSection)
                RETURN chunk.source_report AS report,
                       s.name AS section,
                       chunk.quality_tag AS quality,
                       size([(chunk)-[:EXEMPLIFIES]->() | 1]) AS exemplifies_count
                ORDER BY report, s.order
            """)
            for record in result:
                print(f"  {record['report']} / {record['section']} "
                      f"({record['quality']}) -> {record['exemplifies_count']} 个范例关系")


# ==================== 主流程 ====================
def main():
    print("=" * 70)
    print("GraphRAG Indexer for PBL Report Evaluation (7 Sections)")
    print("=" * 70)

    if not LLM_API_KEY:
        raise ValueError("未配置 OPENAI_API_KEY，无法调用 LLM 标注。")
    if not NEO4J_PASSWORD:
        raise ValueError("未配置 NEO4J_PASSWORD，无法连接 Neo4j。")

    reports_config = _load_reports_config()
    if not reports_config:
        raise ValueError(
            "未配置 SECTION_INDEX_REPORTS。"
            "请设置 JSON 数组，例如："
            '[{"path":"reports/a.docx","name":"优质报告1","quality":"exemplar"}]'
        )

    indexer = GraphRAGIndexer(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    print(f"\n[连接] Neo4j @ {NEO4J_URI}")

    for file_path, report_name, quality_tag in reports_config:
        print(f"\n{'='*70}")
        print(f"处理报告: {report_name} (质量: {quality_tag})")
        print(f"文件路径: {file_path}")

        if not os.path.exists(file_path):
            print(f"  [错误] 文件不存在，跳过: {file_path}")
            continue

        # 读取：docx 用段落级，其他用全文
        if file_path.lower().endswith(".docx"):
            paragraphs = read_docx_paragraphs(file_path)
            print(f"  读取完成，共 {len(paragraphs)} 个段落")
            chunks = split_by_sections(paragraphs, file_path)
        else:
            if file_path.lower().endswith(".pdf"):
                text = read_pdf(file_path)
            elif file_path.lower().endswith(".txt"):
                text = read_txt(file_path)
            else:
                print(f"  [错误] 不支持的文件格式")
                continue
            print(f"  读取完成，总字数: {len(text)}")
            chunks = split_by_sections(text, file_path)

        print(f"  切分完成，找到 {len(chunks)} 个章节")

        # 处理每个章节
        for chunk in chunks:
            section_name = chunk["section"]
            content = chunk["content"]
            print(f"\n  章节: {section_name} (字数: {len(content)})")

            if len(content) < 50:
                print(f"    [警告] 内容过短，跳过 LLM 标注")
                continue

            # 构建 Prompt（只传入相关指标）
            prompt = build_llm_prompt(content, section_name, quality_tag)

            # 调用 LLM
            print(f"    调用 LLM 标注...")
            llm_result = call_llm(prompt)
            exemplifies = llm_result.get("exemplifies", [])

            # 写入 Neo4j
            indexer.create_chunk(
                report_name=report_name,
                section_name=section_name,
                content=content,
                quality_tag=quality_tag,
                exemplifies=exemplifies
            )

    # 3. 验证
    print(f"\n{'='*70}")
    print("索引构建完成，验证图谱...")
    indexer.verify_graph()

    indexer.close()
    print("\n全部完成！")


if __name__ == "__main__":
    main()