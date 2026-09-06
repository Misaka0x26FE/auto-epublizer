"""OCR 抽象：RapidOCR 离线默认。

- OCR 后端可插拔，测试用 fake；
- 无法识别的页面由 agent 逐页阅读兜底（唯一 LLM 原则：CLI 不调用任何模型）；
- 每页记录处理方式，供审查与审计。
"""

from __future__ import annotations

from typing import Protocol


class OcrBackend(Protocol):
    def ocr_image(self, image_path: str) -> str: ...


class RapidOcrBackend:
    """RapidOCR 离线 OCR（可选 extra：rapidocr-onnxruntime）；引擎懒加载。"""

    def __init__(self) -> None:
        try:
            import rapidocr_onnxruntime  # noqa: F401
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "未安装 rapidocr-onnxruntime；请 uv sync --extra ocr，"
                "或改用 MinerU 外部 API / agent 逐页阅读兜底"
            ) from e
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR

            self._engine = RapidOCR()
        return self._engine

    def ocr_image(self, image_path: str) -> str:
        result, _ = self._get_engine()(str(image_path))
        if not result:
            return ""
        return "\n".join(item[1] for item in result)


def create_ocr_backend(backend: str = "rapidocr") -> OcrBackend:
    if backend == "rapidocr":
        return RapidOcrBackend()
    if backend == "fake":
        return FakeOcrBackend()
    raise ValueError(f"未知 OCR 后端：{backend}")


class FakeOcrBackend:
    """测试用 OCR：返回预设文本。"""

    def __init__(self, text: str = "OCR 占位文本") -> None:
        self._text = text

    def ocr_image(self, image_path: str) -> str:
        return self._text
