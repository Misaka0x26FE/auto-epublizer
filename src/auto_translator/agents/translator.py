"""翻译 Agent：段落翻译返回句对 JSON 的提示词封装。"""

from __future__ import annotations

from auto_common.llm.base import LLMClient

_TRANSLATOR_SYSTEM = (
    "你是专业文学/学术译者。将待译正文逐段翻译为目标语言，"
    "严格遵守术语表与文体指引，忠实原文、不漏译不增译、保留分段。"
    '输出 JSON：{"translations": [[句, 句, …], [句, …], …]}，'
    "外层数组长度必须等于输入段落数，每项是该段的译文句子数组。只输出 JSON。"
)


class TranslatorAgent:
    """段落翻译，返回等长句对数组；只依赖 LLMClient。"""

    def __init__(self, client: LLMClient, *, tier: str = "strong") -> None:
        self._client = client
        self._tier = tier

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
        result = self._client.complete_json(
            [
                {"role": "system", "content": _TRANSLATOR_SYSTEM},
                {"role": "user", "content": "\n\n".join(user_parts)},
            ],
            tier=self._tier,
            stage="translate",
        )
        translations = result.get("translations") if isinstance(result, dict) else result
        if not isinstance(translations, list):
            raise RuntimeError("翻译结果缺少 translations 数组")
        # 段级等长兜底：数量不符时按输入段数补齐空数组，交由调用方重试/告警
        out: list[list[str]] = []
        for i in range(len(paragraphs)):
            item = translations[i] if i < len(translations) else []
            if not isinstance(item, list):
                item = [str(item)]
            out.append([str(s) for s in item if str(s).strip()])
        return out
