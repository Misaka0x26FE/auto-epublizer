"""证据取证（G2）与仲裁/修订（G3）Agent。"""

from __future__ import annotations

from typing import Any

from auto_common.llm.base import LLMClient

_EVIDENCE_SYSTEM = (
    "你是翻译取证员。对候选问题，仅基于给定证据裁定 confirmed（确凿）或 dismissed（驳回），"
    '禁止假设未取得的上下文。输出 JSON：{"verdict":"confirmed|dismissed",'
    '"evidence_refs":["glossary:term"],"reason":""}。只输出 JSON。'
)

_ARBITER_SYSTEM = (
    "你是术语仲裁员。跨块对同一术语出现矛盾译法时，终局裁决 suggested（取其一）或 unresolved（证据不足）。"
    '输出 JSON：{"source":"","suggested":"","resolution":"suggested|unresolved","reason":""}。只输出 JSON。'
)

_FIXER_SYSTEM = (
    "你是译文修订员。在最小修改前提下给出完整单句替换，回显 segment_ref、before_hash、"
    '全部 issue_ids，末尾 complete:true。输出 JSON：{"after":"修订后完整译句",'
    '"complete":true}。只输出 JSON。'
)


class EvidenceAgent:
    """G2 取证：confirmed / dismissed。"""

    def __init__(self, client: LLMClient, *, tier: str = "strong") -> None:
        self._client = client
        self._tier = tier

    def adjudicate(self, issue: dict[str, Any], context: str) -> dict[str, Any]:
        result = self._client.complete_json(
            [
                {"role": "system", "content": _EVIDENCE_SYSTEM},
                {
                    "role": "user",
                    "content": f"候选问题：{issue}\n\n可用证据：\n{context}",
                },
            ],
            tier=self._tier,
            stage="evidence",
        )
        return result if isinstance(result, dict) else {"verdict": "dismissed"}


class ArbiterAgent:
    """G3 仲裁：跨块矛盾译法终局裁决。"""

    def __init__(self, client: LLMClient, *, tier: str = "strong") -> None:
        self._client = client
        self._tier = tier

    def arbitrate(self, source: str, targets: list[str], context: str = "") -> dict[str, Any]:
        result = self._client.complete_json(
            [
                {"role": "system", "content": _ARBITER_SYSTEM},
                {
                    "role": "user",
                    "content": f"术语：{source}\n候选译法：{targets}\n{context}",
                },
            ],
            tier=self._tier,
            stage="arbitrate",
        )
        return result if isinstance(result, dict) else {}


class FixerAgent:
    """G3 影子修订：只在 overlay 上给最小修改的完整单句替换。"""

    def __init__(self, client: LLMClient, *, tier: str = "strong") -> None:
        self._client = client
        self._tier = tier

    def fix(self, before: str, issue: dict[str, Any]) -> str:
        result = self._client.complete_json(
            [
                {"role": "system", "content": _FIXER_SYSTEM},
                {
                    "role": "user",
                    "content": f"原译句：{before}\n问题：{issue.get('detail')}\n建议：{issue.get('suggestion')}",
                },
            ],
            tier=self._tier,
            stage="fix",
        )
        if isinstance(result, dict) and result.get("complete") is True and result.get("after"):
            return str(result["after"])
        return before
