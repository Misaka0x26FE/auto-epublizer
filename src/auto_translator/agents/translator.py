"""翻译 Agent：段落翻译返回句对 JSON 的提示词封装。"""

from __future__ import annotations

from typing import Any

from auto_common.llm.base import LLMClient

_TRANSLATOR_SYSTEM = (
    "你是专业文学/学术译者。将待译正文逐段翻译为目标语言，"
    "严格遵守术语表与文体指引，忠实原文、不漏译不增译、保留分段。"
    '输出 JSON：{"translations": [[句, 句, …], [句, …], …]}，'
    "外层数组长度必须等于输入段落数，每项是该段的译文句子数组。只输出 JSON。"
)


class TranslatorAgent:
    """段落翻译，返回等长句对数组；只依赖 LLMClient；数量违例整批重试。"""

    def __init__(
        self, client: LLMClient, *, tier: str = "strong", max_output_retries: int = 2
    ) -> None:
        self._client = client
        self._tier = tier
        self._max_output_retries = max_output_retries

    def translate_batch(
        self,
        paragraphs: list[str],
        *,
        context: str = "",
        terms: list[tuple[str, str]] | None = None,
    ) -> list[list[str]]:
        user_parts: list[str] = []
        if context:
            user_parts.append(context)
        if terms:
            user_parts.append("术语表：" + "；".join(f"{s}={t}" for s, t in terms))
        for i, p in enumerate(paragraphs, start=1):
            user_parts.append(f"[{i}] {p}")
        messages = [
            {"role": "system", "content": _TRANSLATOR_SYSTEM},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ]
        translations: Any = None
        for _ in range(self._max_output_retries + 1):
            result = self._client.complete_json(messages, tier=self._tier, stage="translate")
            translations = result.get("translations") if isinstance(result, dict) else result
            if isinstance(translations, list) and len(translations) == len(paragraphs):
                break
            translations = None
        if translations is None:
            raise RuntimeError(
                f"翻译输出协议违例（translations 数组长度须等于输入段数 {len(paragraphs)}），"
                f"重试 {self._max_output_retries} 次后放弃"
            )
        out: list[list[str]] = []
        for item in translations:
            if not isinstance(item, list):
                item = [str(item)]
            out.append([str(s) for s in item if str(s).strip()])
        return out
