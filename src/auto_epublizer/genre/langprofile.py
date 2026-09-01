"""语言特定指引（langprofile）：与文体无关的语言陷阱提示。"""

from __future__ import annotations

from dataclasses import dataclass

_LANGPROFILES: dict[str, tuple[str, ...]] = {
    "ja": (
        "敬称策略（さん/君/ちゃん/様/先生）三选一：keep_style / normalize / drop",
        "第一人称（私/僕/俺/あたし）定语域与代词须跨段一致",
        "拟声拟态词按中文习惯转写，勿生硬直译",
        "汉字词≠中文词，勿照搬（如「大丈夫」不可译作「大丈夫」）",
        "振假名〘〙仅供判读，严禁写入译文",
    ),
    "en": (
        "无敬称体系，Mr./Ms./Sir 等全书统一处理",
        "据姓名性别与上下文定「他/她/它」，避免代词误用",
        "时态/关系从句/长句按中文重组，被动酌情转主动",
        "专名音译并首现括注原文",
    ),
    "ru": ("忠实传意，符合中文表达习惯；父名/尊称按惯例处理",),
    "ko": ("敬语层级与称谓按语境处理；汉字词转中文时勿照搬",),
    "fr": ("忠实传意，符合中文表达习惯；敬称 vous/tu 语境化",),
    "de": ("忠实传意；复合长词按语义拆分，符合中文表达习惯",),
    "es": ("忠实传意，符合中文表达习惯",),
}

_DEFAULT = ("忠实传意，符合中文目标语言表达习惯",)


@dataclass(frozen=True)
class LangProfile:
    lang: str
    guidance: tuple[str, ...]


def get_langprofile(lang: str) -> LangProfile:
    key = (lang or "").strip().lower().split("-")[0]
    return LangProfile(lang=key, guidance=_LANGPROFILES.get(key, _DEFAULT))
