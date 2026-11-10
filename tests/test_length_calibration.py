"""E1：长度比规则的离线校准（只评估，不改默认阈值）。"""

from __future__ import annotations

import pytest

from auto_translator.review.length_calibration import CalibrationRow, evaluate


def _row(src: str, tgt: str, label: str) -> CalibrationRow:
    return CalibrationRow(src=src, tgt=tgt, label=label)


def test_evaluate_reports_false_positives_and_recall() -> None:
    rows = [
        # 正常压缩（低比值，但人工标注 ok）→ 误报
        _row("This is a fairly long English sentence about history.", "这是关于历史的句子。", "ok"),
        # 整段漏译（目标过短）→ 命中
        _row("Another long English sentence that should be translated fully.", "略", "missing"),
        # 正常长度 → 真负
        _row(
            "Another long English sentence that should be translated fully.",
            "另一句完整的中文译文。",
            "ok",
        ),
        # 空译 → 命中
        _row("Yet another English sentence to translate here.", "", "missing"),
        # 短源行不报警（min_src_chars 保护）
        _row("Note", "", "missing"),
    ]
    result = evaluate(rows)
    assert result["rows"] == 5
    assert result["labels"] == {"ok": 2, "missing": 3}
    # 两个「正常压缩」在 0.30 口径下都告警 → 误报；短源行空译仍命中
    assert result["tp"] == 3 and result["fp"] == 2 and result["fn"] == 0
    assert result["alerts"] == 5
    assert result["precision"] == pytest.approx(3 / 5)
    assert result["recall"] == pytest.approx(1.0)


def test_unknown_label_is_rejected() -> None:
    with pytest.raises(ValueError, match="label"):
        evaluate([{"src": "a", "tgt": "b", "label": "maybe"}])


def test_custom_threshold_changes_alerts_without_hiding_empty() -> None:
    rows = [
        _row("x" * 40, "中" * 20, "ok"),  # ratio 0.5
        _row("x" * 40, "", "missing"),
    ]
    strict = evaluate(rows, too_short=0.6)
    relaxed = evaluate(rows, too_short=0.2)
    assert strict["alerts"] == 2
    assert relaxed["alerts"] == 1  # 空译始终告警
    assert relaxed["fn"] == 0 and relaxed["tn"] == 1  # 0.5 不告警 → 标注 ok 的真负
