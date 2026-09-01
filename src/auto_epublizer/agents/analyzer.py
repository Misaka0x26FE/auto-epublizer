"""分析 Agent：分层理解（全书概览/全局/每单元/重点）与术语播种的提示词封装。"""

from __future__ import annotations

from typing import Any

from ..llm.base import LLMClient

_OVERVIEW_SYSTEM = (
    "你是资深文学编辑与翻译策划。通读以下原文，用中文写出全书内容概要，"
    "覆盖主题、主要人物、情节/论证脉络，控制在 200 字以内，直接输出正文。"
)


_ANALYSIS_SYSTEM = (
    "你是资深翻译编辑。基于给定原文写出结构化的「全局理解」，"
    "以 Markdown 列表输出：主题、叙事人称与时态、文体/语气、跨章依赖/伏笔、高风险处。"
    "直接输出正文，不要输出 JSON。"
)


def _text(messages: list[dict[str, str]]) -> str:
    return "\n\n".join(m["content"] for m in messages if m.get("role") == "user")


class AnalyzerAgent:
    """调用 LLM 生成分析产物；只依赖 LLMClient，不含状态。"""

    def __init__(self, client: LLMClient, *, tier: str = "cheap") -> None:
        self._client = client
        self._tier = tier

    def overview(self, book_text: str) -> str:
        return self._client.complete(
            [
                {"role": "system", "content": _OVERVIEW_SYSTEM},
                {"role": "user", "content": _text([{"role": "user", "content": book_text}])},
            ],
            tier=self._tier,
            stage="analysis_overview",
        )

    def global_understanding(self, book_text: str) -> str:
        return self._client.complete(
            [
                {"role": "system", "content": _ANALYSIS_SYSTEM},
                {"role": "user", "content": _text([{"role": "user", "content": book_text}])},
            ],
            tier=self._tier,
            stage="analysis_global",
        )

    def unit_understanding(self, title: str, unit_text: str, global_ctx: str = "") -> str:
        prompt = f"# {title}\n\n{unit_text}"
        if global_ctx:
            prompt = f"全书概览：\n{global_ctx}\n\n单元原文：\n{prompt}"
        return self._client.complete(
            [
                {"role": "system", "content": _ANALYSIS_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            tier=self._tier,
            stage="analysis_unit",
        )

    def seed_terms(self, text: str, term_types: tuple[str, ...]) -> list[dict[str, Any]]:
        """从原文提取术语，返回 [{source,target,type,aliases,gender,note}]。"""
        type_hint = "、".join(term_types) or "person、place、org、term"
        result = self._client.complete_json(
            [
                {
                    "role": "system",
                    "content": (
                        "你是术语表编辑。从原文提取值得全书统一译法的人名/地名/组织/术语，"
                        "输出 JSON 数组，每项字段：source(原文)、target(译法)、"
                        f"type(仅限 {type_hint})、aliases(别名数组)、gender(仅人物，可为空)、"
                        "note(说明)。只输出 JSON。"
                    ),
                },
                {"role": "user", "content": _text([{"role": "user", "content": text}])},
            ],
            tier=self._tier,
            stage="analysis_terms",
        )
        if isinstance(result, dict):
            result = result.get("terms", result.get("items", []))
        return [t for t in result if isinstance(t, dict) and t.get("source")]

    def characters(self, text: str) -> list[dict[str, Any]]:
        """提取角色圣经（小说）：[{source,reading,target,gender,note}]。"""
        result = self._client.complete_json(
            [
                {
                    "role": "system",
                    "content": (
                        "你是小说编辑。从原文提取主要角色，输出 JSON 数组，每项字段："
                        "source(原文名)、reading(读音，可为空)、target(译名)、"
                        "gender(男/女/其他，可为空)、note(说话方式：自称/口癖/敬语习惯)。只输出 JSON。"
                    ),
                },
                {"role": "user", "content": _text([{"role": "user", "content": text}])},
            ],
            tier=self._tier,
            stage="analysis_characters",
        )
        if isinstance(result, dict):
            result = result.get("characters", result.get("items", []))
        return [c for c in result if isinstance(c, dict) and c.get("source")]
