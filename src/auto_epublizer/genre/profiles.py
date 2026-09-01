"""文体档案（声明式数据）：按 genre 键加载，新增体裁不改代码。

文体档案决定分析维度、术语类型白名单、翻译指引、审校侧重与辅文侧重；
语言指引（langprofile）决定语言陷阱，与文体无关。二者叠加组成注入 prompt 的文体指引。
"""

from __future__ import annotations

from dataclasses import dataclass

GENRES = ("novel", "academic", "paper", "poetry", "newspaper")


@dataclass(frozen=True)
class GenreProfile:
    genre: str
    term_types: tuple[str, ...] = ()
    review_focus: tuple[str, ...] = ()
    translation_rules: tuple[str, ...] = ()
    style_dimensions: tuple[str, ...] = ()
    source_only_types: tuple[str, ...] = ()
    # 小说等叙事体才需要角色圣经
    needs_characters: bool = False


_PROFILES: dict[str, GenreProfile] = {
    "novel": GenreProfile(
        genre="novel",
        term_types=(
            "person",
            "place",
            "org",
            "term",
            "appellation",
            "honorific",
            "speech",
            "fixed_expr",
        ),
        review_focus=("pronoun", "terminology", "consistency"),
        translation_rules=(
            "忠实原文，绝不漏译、增译、合并或拆分段落，保留原文分段",
            "保留叙事人称与语气；对话按角色口癖/自称/敬语译出辨识度",
            "代词指代、人物称谓、语气跨段连贯",
        ),
        style_dimensions=("tone", "narration", "pacing", "register", "dialogue_style", "rhetoric"),
        source_only_types=("appellation", "honorific", "speech", "fixed_expr"),
        needs_characters=True,
    ),
    "academic": GenreProfile(
        genre="academic",
        term_types=("term", "person", "place", "org", "event", "work"),
        review_focus=("terminology", "number_unit", "abbreviation"),
        translation_rules=(
            "学科术语全书统一，缩略语首现加注全称",
            "参考文献条目保留原文不译",
            "数字单位按目标语言规范",
        ),
        style_dimensions=("tone", "register", "citation_style"),
    ),
    "paper": GenreProfile(
        genre="paper",
        term_types=("term", "abbreviation"),
        review_focus=("terminology", "abbreviation"),
        translation_rules=(
            "IMRaD 结构：结果与讨论分离，可复现",
            "缩略语首现加注",
        ),
        style_dimensions=("tone", "register"),
    ),
    "poetry": GenreProfile(
        genre="poetry",
        term_types=("term",),
        review_focus=("line_structure", "imagery"),
        translation_rules=(
            "行结构/分节保留，按行对齐",
            "意象优先，韵脚策略显式声明",
        ),
        style_dimensions=("tone", "imagery", "rhyme"),
    ),
    "newspaper": GenreProfile(
        genre="newspaper",
        term_types=("term", "person", "place", "org"),
        review_focus=("factuality", "headline", "quote"),
        translation_rules=(
            "按版面组织，标题导语化",
            "事实与引语准确，客观转达",
        ),
        style_dimensions=("tone", "register"),
    ),
}


def get_profile(genre: str) -> GenreProfile:
    key = (genre or "").strip().lower()
    return _PROFILES.get(key, _PROFILES["novel"])


def list_genres() -> tuple[str, ...]:
    return GENRES
