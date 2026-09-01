"""审校 Agent（G1）：逐批双语审校，报 issue（宁缺毋滥），不直接改。"""

from __future__ import annotations

from typing import Any

from ..llm.base import LLMClient

_REVIEWER_SYSTEM = (
    "你是严谨的双语审校。对照源句与译句，找出确凿的翻译问题。"
    "问题类型仅限：missing（漏译）、added（增译）、mistranslation（误译）、"
    "terminology（术语违例）、pronoun（人称/性别代词错误）。"
    "宁缺毋滥：合理语序调整、自然意译、风格润色不算问题，拿不准不报。"
    '输出 JSON：{"issues":[{"seq":句号,"type":类型,"detail":说明,"suggestion":建议}],'
    '"reviewed_segments":批内句数,"complete":true}。只输出 JSON。'
)


class ReviewerAgent:
    """G1 审校：返回候选 issue 列表（verdict 未定）。"""

    def __init__(self, client: LLMClient, *, tier: str = "cheap") -> None:
        self._client = client
        self._tier = tier

    def review_batch(
        self,
        pairs: list[dict[str, Any]],
        *,
        terms: list[tuple[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        lines: list[str] = []
        if terms:
            lines.append("术语表：" + "；".join(f"{s}={t}" for s, t in terms))
        for p in pairs:
            lines.append(f"[{p['seq']}] 源：{p['src']}\n    译：{p['tgt']}")
        result = self._client.complete_json(
            [
                {"role": "system", "content": _REVIEWER_SYSTEM},
                {"role": "user", "content": "\n\n".join(lines)},
            ],
            tier=self._tier,
            stage="review",
        )
        if not isinstance(result, dict) or result.get("complete") is not True:
            raise RuntimeError("审校协议违例：缺少 reviewed_segments/complete:true")
        issues = result.get("issues", [])
        return [i for i in issues if isinstance(i, dict)]
