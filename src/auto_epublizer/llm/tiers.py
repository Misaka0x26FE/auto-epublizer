"""模型档位解析：缺档时向更便宜档回退，绝不升级到更贵档。"""

from __future__ import annotations

_TIER_FALLBACK = {"fast": ("cheap", "strong"), "cheap": ("strong",), "strong": ()}


def resolve_tier[T](tiers: dict[str, T], tier: str) -> T:
    if tier in tiers:
        return tiers[tier]
    for fallback in _TIER_FALLBACK.get(tier, ("strong",)):
        if fallback in tiers:
            return tiers[fallback]
    return tiers["strong"]
