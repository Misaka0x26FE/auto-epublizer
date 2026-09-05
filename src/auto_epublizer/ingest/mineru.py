"""MinerU 外部解析 API 后端（确定性外部解析服务，非 LLM）。

扫描件 PDF 的**最优先**解析方案：MinerU 做版面分析 + OCR，能识别换行/段落/
插图/表格/公式——传统 OCR 只识别字符（换行与插图由 agent 逐页阅读兜底，
见 skills/auto-epublizer/lessons/）。密钥只从环境变量 ``MINERU_API_KEY`` 读取，
禁止写入配置文件、源码或提交。

API 契约（https://mineru.net/api/v4，2026-09 实测）：

1. ``POST /file-urls/batch`` 申请预签名上传链接（Bearer token）；
2. ``PUT <file_url>`` 上传原始字节（**不带 Content-Type**，签名敏感）；
3. 轮询 ``GET /extract-results/batch/{batch_id}``，``state`` ∈
   pending/running/done/failed/converting；
4. ``done`` → 下载 ``full_zip_url``：``full.md`` + ``*_content_list.json`` +
   ``images/``（另有 layout.json / *_model.json / *_origin.pdf，不消费）。

``content_list.json``（v1，扁平）每条 ``{type, text?, text_level?, img_path?,
image_caption[]?, image_footnote[]?, table_body?, bbox, page_idx}``，``page_idx``
为 0-based。**caption/footnote 内的文本必须吐回正文**——实测紧随插图的正文行
会被归为 ``image_footnote``，不吐回即丢内容。类型路由：``text``（含
``text_level`` → 标题）/ ``image`` / ``chart``（整页图版也归此类）/ ``table`` /
``equation``；``header``/``footer`` 跳过；未知类型按有无 text/img_path 防御处理。
"""

from __future__ import annotations

import io
import json
import os
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .inserts import InsertRecord, InsertSource, next_insert_id, write_inserts
from .models import KIND_HEADING, KIND_TEXT, SourceDocument, SourceSegment, SourceUnit

DEFAULT_BASE_URL = "https://mineru.net/api/v4"


class MineruError(RuntimeError):
    """MinerU 解析失败（用户可见中文错误）。"""


@dataclass(frozen=True)
class MineruParseResult:
    """一次 MinerU 解析的产物（zip 解包后的内存形态）。"""

    content_list: list[dict[str, Any]] = field(default_factory=list)
    markdown: str = ""
    images: dict[str, bytes] = field(default_factory=dict)  # zip 相对路径 → 字节


class MineruClient:
    """MinerU API v4 薄客户端：batch 上传 → PUT → 轮询 → 下载并解包 zip。

    ``transport`` 可注入 ``httpx.MockTransport`` 供离线确定性测试；
    ``model_version`` 默认 ``pipeline``（确定性、零幻觉），``vlm`` 为可选
    高精度档（内部为 VLM，仅按用户显式配置启用）。
    """

    def __init__(
        self,
        token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 120.0,
        poll_interval: float = 5.0,
        poll_timeout: float = 900.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._poll_timeout = poll_timeout
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self._timeout, transport=self._transport)

    def _api_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def parse_file(
        self,
        path: str | Path,
        *,
        model_version: str = "pipeline",
        language: str = "ch",
        is_ocr: bool = True,
    ) -> MineruParseResult:
        """完整解析流程：申请链接 → 上传 → 轮询 → 下载 zip → 解包。"""
        pdf = Path(path)
        if not pdf.is_file():
            raise MineruError(f"源 PDF 不存在：{pdf}")
        with self._client() as client:
            batch_id, file_url = self._create_batch(
                client, pdf.name, model_version, language, is_ocr
            )
            self._upload(client, file_url, pdf.read_bytes())
            zip_url = self._poll_done(client, batch_id)
            zip_bytes = self._download(client, zip_url)
        return _unpack_zip(zip_bytes)

    def _create_batch(
        self, client: httpx.Client, name: str, model_version: str, language: str, is_ocr: bool
    ) -> tuple[str, str]:
        resp = client.post(
            f"{self._base_url}/file-urls/batch",
            headers=self._api_headers(),
            json={
                "enable_formula": True,
                "enable_table": True,
                "model_version": model_version,
                "language": language,
                "files": [{"name": name, "is_ocr": is_ocr}],
            },
        )
        data = _api_json(resp, "file-urls/batch")
        batch_id = (data.get("data") or {}).get("batch_id") or ""
        file_urls = (data.get("data") or {}).get("file_urls") or []
        if not batch_id or not file_urls:
            raise MineruError(f"MinerU 未返回上传链接：{data.get('msg') or data}")
        return batch_id, file_urls[0]

    def _upload(self, client: httpx.Client, file_url: str, content: bytes) -> None:
        resp = client.put(file_url, content=content)
        if resp.status_code >= 300:
            raise MineruError(f"MinerU 上传失败（HTTP {resp.status_code}）")

    def _poll_done(self, client: httpx.Client, batch_id: str) -> str:
        deadline = time.monotonic() + self._poll_timeout
        while True:
            resp = client.get(
                f"{self._base_url}/extract-results/batch/{batch_id}",
                headers=self._api_headers(),
            )
            data = _api_json(resp, "extract-results/batch")
            results = (data.get("data") or {}).get("extract_result") or []
            state = str(results[0].get("state") or "") if results else ""
            if state == "failed":
                raise MineruError(f"MinerU 解析失败：{results[0].get('err_msg') or '未知原因'}")
            if state == "done":
                zip_url = results[0].get("full_zip_url") or ""
                if not zip_url:
                    raise MineruError("MinerU 任务完成但未返回结果下载地址")
                return zip_url
            if time.monotonic() >= deadline:
                raise MineruError(
                    f"MinerU 解析超时（{int(self._poll_timeout)}s，最后状态 {state or '无响应'}）；"
                    "可重跑或改用 pdf.backend: pymupdf"
                )
            time.sleep(self._poll_interval)

    def _download(self, client: httpx.Client, zip_url: str) -> bytes:
        resp = client.get(zip_url)
        if resp.status_code >= 300:
            raise MineruError(f"MinerU 结果下载失败（HTTP {resp.status_code}）")
        return resp.content


def _api_json(resp: httpx.Response, what: str) -> dict[str, Any]:
    """统一解析 API 响应：HTTP 层与业务 code 层都转中文错误。"""
    if resp.status_code >= 500:
        raise MineruError(f"MinerU 服务异常（HTTP {resp.status_code}，{what}）")
    try:
        data = resp.json()
    except ValueError as e:
        raise MineruError(f"MinerU 响应不是有效 JSON（{what}）") from e
    if resp.status_code >= 400 or data.get("code") not in (0, None):
        raise MineruError(f"MinerU API 错误（{what}）：{data.get('msg') or resp.status_code}")
    return data


def _unpack_zip(zip_bytes: bytes) -> MineruParseResult:
    """解包结果 zip：content_list（v1）+ full.md + images/。"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as e:
        raise MineruError("MinerU 结果不是有效的 zip 包") from e
    with zf:
        content_list: list[dict[str, Any]] = []
        markdown = ""
        images: dict[str, bytes] = {}
        for name in zf.namelist():
            if name.endswith("_content_list_v2.json"):
                continue
            if name == "content_list.json" or name.endswith("_content_list.json"):
                content_list = json.loads(zf.read(name).decode("utf-8"))
            elif name == "full.md":
                markdown = zf.read(name).decode("utf-8")
            elif name.startswith("images/"):
                images[name] = zf.read(name)
    if not content_list:
        raise MineruError("MinerU 结果缺少 content_list.json（解析产物为空？）")
    return MineruParseResult(content_list=content_list, markdown=markdown, images=images)


def _caption_texts(value: Any) -> list[str]:
    """caption/footnote 字段 → 文本列表：兼容 str / {text:…} 两种形态。"""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = item.get("text") if isinstance(item, dict) else item
        if isinstance(text, str) and text.strip():
            out.append(text.strip())
    return out


def _emit_image(
    item: dict[str, Any],
    images: dict[str, bytes],
    records: list[InsertRecord],
    media_dir: Path | None,
) -> list[SourceSegment]:
    """image/chart/table 块 → 媒体文件 + 插入记录 + 引用段（含 caption/footnote 文本）。

    图片字节缺失时不产引用（宁缺毋滥）；caption/footnote 文本按
    「caption 在图前、footnote 在图后」吐回正文，防止正文被吞进图注。
    """
    page = int(item.get("page_idx") or 0) + 1
    caption_key = "table_caption" if item.get("type") == "table" else "image_caption"
    footnote_key = "table_footnote" if item.get("type") == "table" else "image_footnote"
    captions = _caption_texts(item.get(caption_key))
    footnotes = _caption_texts(item.get(footnote_key))

    segments = [
        SourceSegment(
            index=0,
            source=t,
            kind=KIND_TEXT,
            meta={"source_page": page, "source_bbox": item.get("bbox")},
        )
        for t in captions
    ]

    img_path = str(item.get("img_path") or "")
    data = images.get(img_path) if img_path else None
    if data is not None and media_dir is not None:
        insert_type = "table" if item.get("type") == "table" else "image"
        iid = next_insert_id(records, page, insert_type)
        ext = Path(img_path).suffix or ".jpg"
        name = f"{iid}{ext}"
        media_dir.mkdir(parents=True, exist_ok=True)
        (media_dir / name).write_bytes(data)
        extra: dict[str, Any] = {}
        if item.get("table_body"):
            extra["table_body_html"] = item["table_body"]
        records.append(
            InsertRecord(
                id=iid,
                type=insert_type,
                source=InsertSource(page=page, bbox=item.get("bbox"), xref=None, method="mineru"),
                file=f"media/{name}",
                extra=extra,
            )
        )
        segments.append(
            SourceSegment(
                index=0,
                source=f"![{iid}](raw/media/{name})",
                kind=KIND_TEXT,
                meta={
                    "source_page": page,
                    "source_bbox": item.get("bbox"),
                    "insert_id": iid,
                    "insert_type": insert_type,
                },
            )
        )

    segments.extend(
        SourceSegment(
            index=0,
            source=t,
            kind=KIND_TEXT,
            meta={"source_page": page, "source_bbox": item.get("bbox")},
        )
        for t in footnotes
    )
    return segments


def _segments_from_content_list(
    items: list[dict[str, Any]],
    images: dict[str, bytes],
    records: list[InsertRecord],
    media_dir: Path | None,
) -> list[SourceSegment]:
    """content_list（v1）→ 段序列：文本/标题/图/表/公式按阅读顺序原位展开。"""
    segments: list[SourceSegment] = []
    for item in items:
        page = int(item.get("page_idx") or 0) + 1
        itype = str(item.get("type") or "")
        if itype in ("image", "chart", "table"):
            segments.extend(_emit_image(item, images, records, media_dir))
            continue
        if itype == "equation":
            latex = str(item.get("text") or "").strip()
            if not latex:
                continue
            text = latex if latex.startswith("$$") else f"$${latex}$$"
            iid = next_insert_id(records, page, "formula")
            records.append(
                InsertRecord(
                    id=iid,
                    type="formula",
                    source=InsertSource(
                        page=page, bbox=item.get("bbox"), xref=None, method="mineru"
                    ),
                    latex=latex,
                )
            )
            segments.append(
                SourceSegment(
                    index=0,
                    source=text,
                    kind=KIND_TEXT,
                    meta={
                        "source_page": page,
                        "source_bbox": item.get("bbox"),
                        "insert_id": iid,
                        "insert_type": "formula",
                    },
                )
            )
            continue
        if itype in ("header", "footer"):
            continue
        text = str(item.get("text") or item.get("content") or "").strip()
        if not text:
            continue
        level = item.get("text_level")
        meta: dict[str, Any] = {"source_page": page, "source_bbox": item.get("bbox")}
        kind = KIND_TEXT
        if itype == "title" or level:
            kind = KIND_HEADING
            if level:
                meta["mineru_text_level"] = int(level)
        segments.append(SourceSegment(index=0, source=text, kind=kind, meta=meta))
    for i, seg in enumerate(segments):
        seg.index = i
    return segments


def aggregate_mineru_chapters(
    segments: list[SourceSegment], *, book_title: str
) -> list[SourceUnit]:
    """按 MinerU 标题层级切单元：**每个标题（任意层级）都是单元边界**。

    与 pandoc 路径一致（``pandoc_reader`` 对每个 ``#``/``##`` 标题各切一个单元）：
    源文层级 ``text_level`` 原样写入单元 ``meta.heading_level``——EPUB 目录据此
    嵌套（``#``→章、``##``→节），qa 的 ``E_TOC_FLAT`` 才能按源文层级真实校验。
    首个标题前的内容归 frontmatter；无任何标题信号时保持单单元。
    """
    headings = [
        (i, s)
        for i, s in enumerate(segments)
        if s.kind == KIND_HEADING and s.meta.get("mineru_text_level")
    ]
    if not headings:
        return [
            SourceUnit(
                id="ch01",
                kind="chapter",
                title=book_title,
                segments=segments,
                meta={"aggregated": True, "parser": "mineru"},
            )
        ]

    units: list[SourceUnit] = []
    first_i = headings[0][0]
    if first_i > 0:
        units.append(
            SourceUnit(
                id="fm01",
                kind="frontmatter",
                title=book_title,
                segments=segments[:first_i],
                meta={"aggregated": True, "parser": "mineru"},
            )
        )
    for idx, (start, head) in enumerate(headings):
        end = headings[idx + 1][0] if idx + 1 < len(headings) else len(segments)
        level = int(head.meta["mineru_text_level"])
        units.append(
            SourceUnit(
                id=f"ch{idx + 1:02d}",
                kind="chapter",
                title=head.source.strip(),
                segments=[head, *segments[start + 1 : end]],
                meta={"aggregated": True, "parser": "mineru", "heading_level": level},
            )
        )
    return units


def read_mineru(
    path: str | Path,
    *,
    raw_dir: str | Path | None = None,
    token: str | None = None,
    model_version: str = "pipeline",
    language: str = "ch",
    client: MineruClient | None = None,
) -> SourceDocument:
    """MinerU 解析 PDF → SourceDocument（扫描件最优先路径）。

    落盘（``raw_dir`` 提供时）：``raw/media/`` 插图、``raw/inserts/`` 描述文件、
    ``raw/mineru/``（content_list.json + full.md，审查对账的 ground truth）。
    """
    if client is not None:
        resolved = client
    else:
        key = token or os.environ.get("MINERU_API_KEY", "")
        if not key:
            raise MineruError(
                "未配置 MINERU_API_KEY 环境变量（MinerU 为扫描件首选解析方案，"
                "请向用户询问 API key 后 export）"
            )
        resolved = MineruClient(key)
    result = resolved.parse_file(path, model_version=model_version, language=language)

    raw_path = Path(raw_dir) if raw_dir is not None else None
    media_dir = (raw_path / "media") if raw_path is not None else None
    records: list[InsertRecord] = []
    segments = _segments_from_content_list(result.content_list, result.images, records, media_dir)

    book_title = Path(str(path)).stem
    if raw_path is not None:
        mineru_dir = raw_path / "mineru"
        mineru_dir.mkdir(parents=True, exist_ok=True)
        (mineru_dir / "content_list.json").write_text(
            json.dumps(result.content_list, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (mineru_dir / "full.md").write_text(result.markdown, encoding="utf-8")
        write_inserts(raw_path, records)

    page_count = max(
        (int(item.get("page_idx") or 0) + 1 for item in result.content_list), default=0
    )
    units = aggregate_mineru_chapters(segments, book_title=book_title)
    return SourceDocument(
        title=book_title,
        source_path=os.path.abspath(str(path)),
        fmt="pdf",
        units=units,
        meta={"pages": page_count, "parser": "mineru"},
    )
