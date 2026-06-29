"""PBL 评分共享 Pydantic 模型与 LLM 客户端。"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from openai import OpenAI
from pydantic import BaseModel, Field

from agents.group_project.pbl_config import DEEPSEEK_BASE_URL, DEFAULT_MODEL

from .scoring_utils import safe_json_loads


class SingleScore(BaseModel):
    score: int = Field(..., ge=1, le=5)
    reason: str
    evidence: List[str] = Field(default_factory=list)
    reference_comparison: str = ""
    weakness: str = ""
    suggestion: str = ""


class DimensionScoreSummary(BaseModel):
    dimension_key: str
    dimension_name: str
    student_dimension_text: str = ""
    student_dimension_debug: Dict[str, Any] = Field(default_factory=dict)
    scores: List[SingleScore]
    mean: float
    std: float
    cv: Optional[float]
    min_score: float
    max_score: float
    consistency_level: str
    summary_comment: str


class FinalGradeReport(BaseModel):
    dimension_summary: List[Dict[str, Any]]
    dimension_summary_text: str
    dimension_results: Dict[str, DimensionScoreSummary]
    strengths: List[str]
    weaknesses: List[str]
    revision_suggestions: List[str]
    risk_flags: List[str]
    final_comment: str


class DeepSeekClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        base_url: str = DEEPSEEK_BASE_URL,
        temperature: float = 0.0,
        top_p: float = 0.9,
        max_tokens: int = 4000,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError(
                "缺少 API Key。请在项目根目录 .env 中设置 OPENAI_API_KEY 或 DEEPSEEK_API_KEY。"
            )

        normalized_base = base_url.rstrip("/")
        if "deepseek.com" in normalized_base and not normalized_base.endswith("/v1"):
            normalized_base = f"{normalized_base}/v1"

        self.client = OpenAI(api_key=self.api_key, base_url=normalized_base)
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        retry: int = 3,
    ) -> Dict[str, Any]:
        last_error: Optional[Exception] = None
        for attempt in range(1, retry + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=self.temperature if temperature is None else temperature,
                    top_p=self.top_p,
                    max_tokens=self.max_tokens,
                    stream=False,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("模型返回为空。")
                return safe_json_loads(content)
            except Exception as exc:
                last_error = exc
                time.sleep(1.2 * attempt)
        raise RuntimeError(f"LLM API 调用失败，最后错误：{last_error}")

    def chat_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        retry: int = 3,
    ) -> str:
        last_error: Optional[Exception] = None
        for attempt in range(1, retry + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=self.temperature if temperature is None else temperature,
                    top_p=self.top_p,
                    max_tokens=self.max_tokens,
                    stream=False,
                )
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("模型返回为空。")
                return content
            except Exception as exc:
                last_error = exc
                time.sleep(1.2 * attempt)
        raise RuntimeError(f"LLM API 调用失败，最后错误：{last_error}")


__all__ = [
    "DeepSeekClient",
    "DimensionScoreSummary",
    "FinalGradeReport",
    "SingleScore",
]
