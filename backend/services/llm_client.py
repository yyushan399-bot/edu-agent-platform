"""LLM 调用封装 —— 调用 OpenAI 兼容 API 进行评估."""

import json
from typing import Optional

import httpx

from backend.config import settings

# 尝试导入现有 prompt 模板（可选）
try:
    from prompts.agent_templates import build_agent_prompt, build_meta_eval_prompt
    HAS_PROMPTS = True
except ImportError:
    HAS_PROMPTS = False


class LLMClient:
    """轻量 LLM 调用客户端."""

    def __init__(self):
        self.api_key = settings.llm_api_key
        self.base_url = settings.llm_base_url
        self.model = settings.llm_model
        self.client = httpx.Client(timeout=120)

    def _call(self, messages: list[dict]) -> str:
        """调用 LLM 并返回文本响应。"""
        if not self.api_key:
            # Mock 模式：返回假数据便于开发调试
            return json.dumps({
                "scores": {"concept_accuracy": 4, "logic_integrity": 3, "theory_transfer": 4},
                "feedbacks": {"concept_accuracy": "概念理解清晰，表述准确。", "logic_integrity": "论证结构合理，但可以更深入。", "theory_transfer": "能将理论应用于实践。"},
                "summary": "整体表现良好，建议在理论深度上进一步挖掘。",
                "dimension_score": 3.67,
            }, ensure_ascii=False)

        resp = self.client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": messages,
                "temperature": 0.3,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def evaluate_dimension(self, dim_key: str, content: str) -> Optional[dict]:
        """对某个维度进行评估，返回解析后的 dict. """
        if HAS_PROMPTS:
            messages = build_agent_prompt(dim_key, content)
        else:
            messages = self._fallback_prompt(dim_key, content)

        try:
            raw = self._call(messages)
            # 尝试提取 JSON
            parsed = self._extract_json(raw)
            parsed["dim_key"] = dim_key
            return parsed
        except Exception as e:
            print(f"[LLM] {dim_key} 评估失败: {e}")
            return None

    def generate_meta_report(self, scores_detail: dict, total_score: float) -> str:
        """生成元评估综合报告。"""
        if HAS_PROMPTS:
            messages_content = build_meta_eval_prompt(
                scores_detail=scores_detail,
                collaboration_score=0,
                self_cal_data={},
                peer_cal_data={},
            )
            messages = [{"role": "user", "content": messages_content}]
        else:
            report_json = json.dumps(scores_detail, ensure_ascii=False, indent=2)
            messages = [
                {"role": "system", "content": "你是教育评估智能体，负责生成综合反馈报告。"},
                {"role": "user", "content": f"请根据以下评估结果生成综合报告：\n{report_json}\n总分：{total_score}"},
            ]

        try:
            raw = self._call(messages)
            return raw
        except Exception as e:
            print(f"[LLM] 元评估失败: {e}")
            return f"## 综合评估报告\n\n总分：{total_score}\n\n（报告生成失败）"

    def _extract_json(self, text: str) -> dict:
        """从 LLM 回复中提取 JSON。"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 查找 ```json ... ```
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            return json.loads(match.group(1).strip())

        # 查找最外层 {}
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group(0))

        raise ValueError(f"无法从 LLM 响应中提取 JSON:\n{text[:200]}")

    def _fallback_prompt(self, dim_key: str, content: str) -> list[dict]:
        """无 prompts 模块时的备用 prompt。"""
        dim_names = {
            "theory": "理论维度",
            "practice": "实践维度",
            "data": "数据维度",
            "literature": "文献维度",
        }
        system = f"""你是教育评估智能体，专门负责从{dim_names.get(dim_key, dim_key)}评价学生的项目报告。
请对每个二级指标进行 1-5 分评分，并给出具体反馈。

请严格按照 JSON 格式返回：
{{
    "scores": {{"indicator_1": 4, ...}},
    "feedbacks": {{"indicator_1": "反馈文字"}},
    "summary": "整体评语",
    "dimension_score": 3.67
}}"""
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": f"请评估以下学生提交内容：\n\n{content}"},
        ]
