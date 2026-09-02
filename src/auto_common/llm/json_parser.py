"""模型 JSON 输出的宽松解析（json-repair 兜底）。"""

from __future__ import annotations

import json
from typing import Any

from json_repair import repair_json


class JsonParseError(ValueError):
    """模型回复在本地修复后仍不是可用 JSON。"""


def parse_json_loose(text: str) -> Any:
    raw = (text or "").strip()
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass

    try:
        value = repair_json(raw, return_objects=True, skip_json_loads=True)
    except Exception as error:
        raise JsonParseError(f"无法解析为 JSON：{raw[:200]!r}") from error
    if value == "":
        raise JsonParseError(f"无法解析为 JSON：{raw[:200]!r}")
    return value
