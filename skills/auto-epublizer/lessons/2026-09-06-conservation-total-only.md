# 守恒类校验必须做单元级总量比对（行级比对会被拆并句误报）

> 来源：`docs/plans/2026-09-06-adoption-plan.md` S1.2/S4.1 实施验证。
> 去向：`review/g0.py::g0_unit_flags`（marker/footnote 总量守恒）、
> `review/fidelity.py`（块级拼接匹配）。

## 判据

需要对「源文中的离散记号」（插入标记、脚注标记、图片引用、表格等）做
src↔tgt 守恒校验时：

- **行级比对**（逐 align 行比 src/tgt 的记号数）会误报——拆句/并句会把记号
  挪到相邻行（如 src 第 1 行的 `[^1]` 在译文里落在第 2 行），行级计数不相等
  但单元总量相等，这不是缺陷。
- **单元级总量比对**（sum over rows）恰好对应「一个都不能丢」的语义：总量
  不等必是丢失/杜撰，总量相等则记号无论怎么挪位都安全。

同理，块级内容匹配（源保真）用**规范化拼接子串**（去全部空白后 concat 再
`in` 判断），天然容忍拆并句与句序调整；不要做行级一一对应。

## 处置

1. 守恒校验在循环内累计两侧总量，循环结束后比对一次，flag 的 data 带
   `{src: N, tgt: M}` 供定位。
2. 内容匹配用 `norm_text`（去空白）+ 拼接子串；反向校验（align src 是否
   抄自源文）语料用**全部非空行**（含标题行），前向校验（源文块是否全被
   翻译）语料**跳标题行**——agent 可把标题作为首行 src。
3. 每个守恒不变量配两个测试：丢失必报 + 挪位不误报（见
   `test_g0_marker_conservation` / `test_g0_footnote_conservation`）。

## 验证

- `tests/test_review.py`：marker 丢失报 `{src:2, tgt:1}`、挪位 0 flag；
  pandoc/数字式脚注同理。
- `tests/test_review.py::test_fidelity_tolerates_split_merge`：拆并句/句序
  调整 0 flag。
