# 第三方许可证（THIRD_PARTY_LICENSES）

本项目自身代码采用 **AGPL-3.0**（见 `LICENSE`）。以下列出直接运行时与开发依赖的许可证。
运行时依赖打包进 wheel 分发；`[ocr]` 可选 extra 与 dev 依赖仅在用户侧安装。

## 运行时依赖

| 包 | 用途 | 许可证 |
|---|---|---|
| typer | CLI 框架 | MIT |
| pydantic | 配置/数据模型 | MIT |
| rich | 终端输出 | MIT |
| httpx | HTTP 客户端（doctor 网络探测） | BSD-3-Clause |
| pyyaml | 配置解析 | MIT |
| lxml | XML 处理 | BSD-3-Clause |
| pymupdf | PDF 文字层抽取 | AGPL-3.0（兼容，可同许可引入） |

## 可选依赖（[ocr] extra）

| 包 | 用途 | 许可证 |
|---|---|---|
| rapidocr-onnxruntime | 离线 OCR | Apache-2.0 |

## 开发依赖

| 包 | 用途 | 许可证 |
|---|---|---|
| pytest | 测试 | MIT |
| ruff | lint / 格式 | MIT |
| hatchling | 构建后端 | MIT |

## 运行时外部二进制（不打包，按文档调用）

| 工具 | 用途 | 许可证 |
|---|---|---|
| pandoc | 非 PDF 格式归一化 | GPL-2.0-or-later |
| epubcheck | EPUB 结构校验 | BSD-3-Clause（EPUB Checker） |

## 说明

- **AGPL 依赖**（pymupdf）与项目同为 AGPL，可直接引入；其余依赖各自保留许可证，
  不随项目许可变更。
- 许可文本以各包随附的 `LICENSE`/`COPYING` 文件为准；本表为概览，不构成法律建议。
