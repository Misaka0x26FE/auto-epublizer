# QA（epubcheck + 解包审计）

`qa` 命令对成品 EPUB 做结构 QA（G4），写 `report.json`。

## 命令

```bash
auto-epublizer qa [--epub <path>] [--workspace <dir>]
# 输出：G4 审计：pass/fail；epubcheck errors：N；passed：true/false
```

## epubcheck

- 用 `~/.cache/epubcheck.jar`（`java -jar`）校验，零 error 放行。
- jar 缺失时 `available=False`、`ran=False`、`errors=-1`，`passed=False`（未验证 ≠ 合格）。

## 解包逐项审计（离线，零 token）

| 检查 | 失败码 |
|---|---|
| 非 zip | `E_NOT_EPUB` |
| mimetype 非首位 / 被压缩 / 内容错 | `E_MIMETYPE_FIRST` / `E_MIMETYPE_STORED` / `E_MIMETYPE_CONTENT` |
| 缺 container.xml / 未声明 OPF | `E_NO_CONTAINER` / `E_CONTAINER_OPF` |
| OPF 缺失 | `E_OPF_MISSING` |
| spine idref 未在 manifest | `E_SPINE_REF` |
| manifest href 无法解析 | `E_MANIFEST_HREF` |
| nav 链接无法解析 | `E_NAV_HREF` |
| javascript:/data: URL 注入 | `E_UNSAFE_URL` |
| 内容文档缺 lang / h1 数量不为 1 | `W_NO_LANG` / `W_H1_COUNT`（告警） |

## 质量报告 `report.json`

```json
{"slug":"...","g4_audit":"pass","g4_epubcheck_errors":0,"passed":true,
 "audit":{"ok":true,"errors":0,"findings":[]},
 "epubcheck":{"available":true,"ran":true,"errors":0,"warnings":0}}
```

## 放行条件（G5）

- `g4_epubcheck_errors == 0`（epubcheck 已实际运行）
- `g4_audit == "pass"`（解包审计零 error）
- 审校 `g2_confirmed == 0` 或全部已修订

## 排查

- `epubcheck errors: -1` → 未装 jar；装 `~/.cache/epubcheck.jar` 后重跑。
- `成品不存在` → 先 `build` 或 `convert`。
- 审计发现 `W_H1_COUNT` → 内容文档标题层级问题（每章应恰一个 h1）。
