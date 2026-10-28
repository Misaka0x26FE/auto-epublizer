> **中文** | [English](2026-10-27-scanned-academic-false-green.md)

# 扫描学术书：机械全绿不是内容验收

## 触发与状态

来自一次 21 单元扫描学术书翻译、审查、人物表重排和版本打包。
不包含书籍正文或用户材料。完整问题矩阵见
[现场报告 #69](https://github.com/Misaka0x26FE/auto-epublizer/issues/69)，
审校覆盖缺陷见 [#68](https://github.com/Misaka0x26FE/auto-epublizer/issues/68)。
初始核查为本地 `a3aee9e`；提交前已在上游 main `ef06f25` 重跑下列复现。

**状态：经验与方案提交，不是代码缺口已修复，也不是原书已完成重新语义验收。**
既有工具能力、现场绕行、操作失败和待开发建议必须分开。

## 判据与处置矩阵

| # | 判据 / 责任边界 | 正确处置与验证 |
|---|---|---|
| 1 | reviewed/built 的 import 默认跳过；失败=0 不等于重校验 | 已有 `import --force` 是交付后重登记入口（#13）；核对实际校验/回退状态，再 build/qa |
| 2 | 历史初次 import 失败=0 仍报术语硬缺陷 | 尚无当前版本最小复现；保存版本、原始命令及 JSON 再报回归，不把旧摘要当复现 |
| 3 | 中文句内残留英文，但原样复制门不触发 | 候选词扫描覆盖正文/辅文/语义注释，agent 逐项判断；人名、缩写、书目和代码不能一律删除；#54 不是混合语言识别器 |
| 4 | 上千 length advisory 掩盖真实漏译 | 按单元聚合、排序并结合语种/体例判断（#39/#54）；保持真实内容，禁止添加填充文字消告警 |
| 5 | OCR 乱码、断词、跨页断句或整段缺失 | 读 PDF 页图和邻页，以实际内容重建 structured/translation/align 并留 repair 证据（#14/#38/#58）；删残句、补句号/省略号不能证明补齐 |
| 6 | 双栏人物表中姓名与职务/任期交叉 | 先保留 page/bbox/column 证据，再按原页建立条目清单；一人一段，每项核对姓名、生卒年、职务、任期、分类及阅读顺序（#58） |
| 7 | 本地脚本用 zip 按块顺序对齐，块数不等时补尾块 | 停下，不凑数；冻结条目清单，显式建立对应；同块数和源保真都不证明语义对应。该脚本不是上游功能 |
| 8 | 登记注数与 aside 数相等，却未清点全部源注 | 源页逐章盘点，独立核证裸数字候选、跨页尾部和跳号；615 条只是现场登记数，不是原书总注数证明（#37/#46/#58） |
| 9 | 按篇幅比例分配尾注，复制“续”或通用补句凑长度 | 这是操作失败，不能推广；逐注回源建立 source note_id→target 完整内容与证据，未核证保持未决（#57） |
| 10 | 注号被闭引号、空格、量词影响，OCR 数字有歧义 | 以原页和 Notes 核证，保持稳定 ref_id；不可改数字或标点迎合正则（#22/#29/#34） |
| 11 | 批量把 formula 判成 OCR 假阳性并填占位 LaTeX | 每个 bbox 读图裁定；真公式写真实 LaTeX，假阳性留个别证据；未核证不能批量结案。描述非空只证明字段非空 |
| 12 | 局部新 review 清零旧全书问题 | 当前路径排序取最新缺继承契约（#68）；保留历史，逐项列出旧问题状态与关闭证据，不让局部 clean 代替全书复核 |
| 13 | JPX 封面为 octet-stream，OPF-012/MED-003；文件名被当图注 | 现场绕行：转真实 JPEG 并同步引用，不只改扩展名；图注写内容，再 build/epubcheck 并检查真实封面；规范化自动修复尚未提交 |
| 14 | title 回声正文在 align 容错剔除，md 却重复 | 确认为家具才删译文重复正文，保留现行 title 容错所需 align 行；核验 drift 和成品。不能全删首段或用缩进标题掩盖 |
| 15 | CJK 空格、游离引号、段末未收束 | 区分出版信息/索引与断句，逐处回源；引号按对判断，不全局加句号或删引号（#38） |
| 16 | 本地打包缺 zhconv；批次误选、版本元数据重复键 | 临时安装只是绕行；建议正式声明依赖并预检，验证批次键唯一及版本一致，异常拒绝打包。属于工作根脚本，不声称上游有同名缺陷（#47） |
| 17 | 有本地 commit/副本，却未核验 tag/push | 保留旧副本只读；验证当前报告时效、逐件 sha256、版本/清单/tag 对应及远端。复制成功或已有目录被跳过不等于验收完成 |
| 18 | 少量 grep/计数被写成全量语义核验 | 审计用 pass/fail/unknown/manual，明确执行范围和未做阅读器测试；不能固定打勾或把未执行写为完成（#57） |

## 复现与验证

以下完全合成，可在仓库环境 `uv run python` 中运行，无网络、无书稿。
它刻画当前能力边界，**不提供改写正文迁就检测器的建议**。

```python
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from auto_epublizer.qa.artifacts import latest_review_result_path
from auto_translator.review.g0 import footnote_numbers, language_identical

assert not language_identical("The committee continued its work.", "委员会 continued 工作。")
assert footnote_numbers("“示例”40，接下文") == set()
assert footnote_numbers("“示例”。40 接下文") == {40}
assert footnote_numbers("句末。65 年龄") == set()
assert footnote_numbers("句末。65 就年龄而言") == {65}

with TemporaryDirectory() as d:
    root = Path(d)
    for name, result in [
        ("review-20261026-comprehensive", {"g2_confirmed": 24, "g3_patched": 0}),
        ("review-20261027-local", {"g2_confirmed": 0, "g3_patched": 0}),
    ]:
        path = root / name / "result.json"
        path.parent.mkdir()
        path.write_text(json.dumps(result), encoding="utf-8")
    selected = latest_review_result_path(SimpleNamespace(reviews_dir=root))
    assert selected.parent.name == "review-20261027-local"
```

代码位置（基线行号）：`src/auto_epublizer/qa/artifacts.py:28` 选择最新路径、
`:130` 只摘要所选 result；`src/auto_epublizer/qa/report.py:99` 读计数、
`:167` 判断 confirmed 是否全部 patched；
`src/auto_translator/review/g0.py:204` 提取注号、`:308` 检查原样复制。
这些结果不能等同于完整 EPUB 放行复现。

双栏合成反例：左栏 Alice/Editor、右栏 Bob/Scientist，扁平化成
Alice/Bob/Editor/Scientist；两侧各四块也可能错误配对。恢复时必须核证
Alice→Editor、Bob→Scientist，不能只比较块数。源页及条目清单才是裁定依据。

## 待开发契约与验收

- 审校问题稳定 ID、范围、输入摘要、继承/替代和逐项关闭证据；局部 clean 不关闭其他范围。
- 摘要覆盖所有有效问题及结案证据，不只“最新”文件；无继承关系时报告 unknown/未结清；兼容旧格式。
- 离线坏样本覆盖审校排序/局部覆盖、混合语言候选、注号上下文、多栏与跨页源清点。
- 机器只提供候选和一致性证据，不自动猜译名、补注文、判公式或恢复语义。

本篇不替代 [交付审计](../references/delivery.zh.md)、
[注释契约](../references/notes.zh.md) 与 [语义整备](../references/repair.zh.md)。
发现旧交付结论过强时应新增更正记录，不能回改历史副本或宣称未经执行的全量复核。
