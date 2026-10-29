# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Misaka0x26FE
"""OCR 抽象：RapidOCR 离线默认。

- OCR 后端可插拔，测试用 fake；
- 结构化接口 ``ocr_lines`` 保留每行的**渲染图像素坐标**与置信度；只有 ``ocr_image``
  的旧后端仍可用（单块、无坐标，读取器不虚构几何）；
- 无法识别的页面由 agent 逐页阅读兜底（唯一 LLM 原则：CLI 不调用任何模型）；
- 每页记录处理方式，供审查与审计。

引擎适配：优先新版 ``rapidocr``（3.x，返回 ``RapidOCROutput``），失败回落
``rapidocr_onnxruntime``（1.x，返回 ``(结果, 耗时)``）。两者都只做本地推理。
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class OcrLine:
    """一行 OCR 结果：文本 + 渲染图像素坐标 ``(x0, y0, x1, y1)`` + 置信度。"""

    text: str
    bbox: tuple[float, float, float, float] | None = None
    confidence: float | None = None


class OcrBackend(Protocol):
    def ocr_image(self, image_path: str) -> str: ...


def _quad_bbox(box: Any) -> tuple[float, float, float, float] | None:
    """四点多边形 / 矩形 → (x0, y0, x1, y1)；形态不认识时返回 None（不猜坐标）。"""
    try:
        points = [(float(p[0]), float(p[1])) for p in box]
    except (TypeError, ValueError, IndexError):
        return None
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _score(value: Any) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if 0.0 <= score <= 1.0 else None


def lines_from_engine_result(result: Any) -> list[OcrLine]:
    """把两种 RapidOCR 引擎返回值归一为 :class:`OcrLine` 列表。

    新版返回 ``RapidOCROutput``（``txts``/``boxes``/``scores`` 并列数组），旧版返回
    ``([box, text, score], elapsed)``。空结果返回空列表。
    """
    if result is None:
        return []
    if hasattr(result, "txts"):
        # 新版字段可能是 tuple、list 或 numpy 数组：不能用 `or ()` 判空。
        texts = getattr(result, "txts", None)
        boxes = getattr(result, "boxes", None)
        scores = getattr(result, "scores", None)
        texts = () if texts is None else texts
        boxes = () if boxes is None else boxes
        scores = () if scores is None else scores
        lines: list[OcrLine] = []
        for index, text in enumerate(texts):
            if not str(text).strip():
                continue
            box = boxes[index] if index < len(boxes) else None
            score = scores[index] if index < len(scores) else None
            lines.append(OcrLine(str(text), _quad_bbox(box), _score(score)))
        return lines
    # 旧版：(结果列表, 耗时)；这里只取结果列表。
    if isinstance(result, tuple) and len(result) == 2 and not _looks_like_line(result[0]):
        result = result[0]
    if result is None:
        return []
    lines = []
    for item in result:
        try:
            box, text, score = item[0], item[1], item[2]
        except (TypeError, ValueError, IndexError):
            continue
        if not str(text).strip():
            continue
        lines.append(OcrLine(str(text), _quad_bbox(box), _score(score)))
    return lines


def _looks_like_line(item: Any) -> bool:
    """区分旧版结果项 ``[box, text, score]`` 与 ``(列表, 耗时)`` 包装。"""
    return isinstance(item, (list, tuple)) and len(item) >= 3 and isinstance(item[1], str)


class RapidOcrBackend:
    """RapidOCR 离线 OCR（可选 extra：``ocr``）；引擎懒加载。"""

    def __init__(self) -> None:
        if importlib.util.find_spec("rapidocr") is not None:
            self._flavor = "rapidocr"
        elif importlib.util.find_spec("rapidocr_onnxruntime") is not None:
            self._flavor = "rapidocr_onnxruntime"
        else:  # pragma: no cover - 环境相关
            raise RuntimeError(
                "未安装 rapidocr / rapidocr-onnxruntime；请 uv sync --extra ocr，"
                "或改用 MinerU 外部 API / agent 逐页阅读兜底"
            )
        self._engine = None

    def _get_engine(self):
        if self._engine is None:  # pragma: no cover - 需要真实引擎
            if self._flavor == "rapidocr":
                from rapidocr import RapidOCR
            else:
                from rapidocr_onnxruntime import RapidOCR
            self._engine = RapidOCR()
        return self._engine

    def ocr_lines(self, image_path: str) -> list[OcrLine]:
        """结构化识别：每行带渲染图像素坐标与置信度。"""
        return lines_from_engine_result(self._get_engine()(str(image_path)))

    def ocr_image(self, image_path: str) -> str:
        return "\n".join(line.text for line in self.ocr_lines(image_path))


def rapidocr_available() -> bool:
    """RapidOCR（新版或旧版包）是否可导入（能力探测，属 OCR 域；路由由编排层决定）。

    C 组最小重构：原 orchestrator 内联 ``importlib.util.find_spec`` 探测，现归
    ``ingest.ocr``（与 doctor 的探测同口径），编排层只读取该结果做装配。
    """
    return (
        importlib.util.find_spec("rapidocr") is not None
        or importlib.util.find_spec("rapidocr_onnxruntime") is not None
    )


def create_ocr_backend(backend: str = "rapidocr") -> OcrBackend:
    if backend == "rapidocr":
        return RapidOcrBackend()
    if backend == "fake":
        return FakeOcrBackend()
    raise ValueError(f"未知 OCR 后端：{backend}")


class FakeOcrBackend:
    """测试用 OCR：返回预设文本（单行、无坐标，便于固定既有断言）。"""

    def __init__(self, text: str = "OCR 占位文本") -> None:
        self._text = text

    def ocr_lines(self, image_path: str) -> list[OcrLine]:
        return [OcrLine(self._text)]

    def ocr_image(self, image_path: str) -> str:
        return self._text
