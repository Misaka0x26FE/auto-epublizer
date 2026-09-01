# 质量控制办法（历史实践提炼）

从两份历史工作成果提炼，作为 auto-epublizer 质量控制的**正向目标**（必须做到）与
**负面限制**（必须避免）。

来源：
- `~/work/translate/` —— 11 本出版物全流水线翻译经验（`出版物结构与处理规范.md`、
  各书 `_理解日志.md`、`QA报告.md`、`qa_findings.md`、`GLOSSARY.csv`）；
- `~/github/epub-builder` —— Go 实现的 EPUB 组织/构建/验证 CLI（`PROGRESS.md`、
  `specification.md`、`qa.md`、`review.md`），已迭代到 release 门禁。

---

## 一、正向目标（必须做到）

### A. 内容完整性：不丢失、不重复

| 目标 | 经验来源 | 落点 |
|---|---|---|
| 拒绝孤立内容（Block 不在任何 flow） | epub-builder `E_BLOCK_NOT_IN_FLOW` | G0/G4 结构审计：每单元必在内容树中 |
| 拒绝重复引用（同 flow 内重复、跨 flow 重复） | `E_DUPLICATE_FLOW_REF` | 内容树验证不变量 |
| "来源存在则必须纳入"（SourceCatalog 清单） | epub-builder SourceCatalog | `structured/` 拆分时登记来源清单，验证全覆盖 |
| 插入元素标记数量守恒（`{fig:NNN}` 32/32） | morris qa_findings「标记数量守恒」 | G0 对照表/标记守恒检查 |
| 脚注注码守恒（1:1） | morris「注码守恒」、fleming 脚注抽样 | G0 脚注引用↔定义配对 |
| 段落块数量 1:1（允许页断残句合并的合理差异） | morris「段落块数量 16/21 完全 1:1」 | G0 句/段数一致 |
| h1/h2 层级数量与源文一致 | morris「h1/h2 层级数量一致」 | G0 标题层级校验 |

### B. 结构正确

| 目标 | 经验来源 | 落点 |
|---|---|---|
| 分阶段验证 structure → freeze → release | epub-builder 三阶段门禁 | `qa` 命令分阶段，release 门禁阻断放行 |
| release 四必需组件（封面/元数据/正文/导航） | epub-builder `E_REQUIRED_*` | G4/G5 放行条件 |
| 稳定 ID（canonical address，非文件名/行号/页码） | epub-builder Node/Block/Insert ID | 我们的单元稳定 ID |
| epub:type 语义（frontmatter/bodymatter/backmatter/bibliography/index/appendix） | epub-builder Phase 6 | 四层结构 → epub:type 映射 |
| lang/xml:lang、landmarks nav、NCX/OPF 元数据正确 | epub-builder Phase 6 | G4 EPUB 审计项 |
| TOC 映射表（层级/原文标题/中文标题/原始页码/PDF页码） | 出版物规范 1.2 | `analysis/` 或 publication.json 的 TOC 映射 |
| 章节类型分类（叙事/论证/混合/资料） | 出版物规范 1.3 | `analysis/units/` 标注章节类型，驱动翻译策略 |

### C. 可追溯

| 目标 | 经验来源 | 落点 |
|---|---|---|
| 原图优先，AI 识别是补充层（`<details>`），不覆盖原件 | epub-builder「原图优先 + Supplement」 | 表格/公式/插图：原始图片 + 识别补充层 |
| 注释双重定位（绝对位置 + 相对位置） | epub-builder NoteRecord 双定位 | 脚注：源页绝对位置 + 正文锚点相对位置 |
| 确定性序号（1,2,3 而非内部 ID） | epub-builder「确定性序号」 | 脚注/尾注编号每章从 1 连续 |
| Asset SHA-256 绑定、内容 hash 校验 | epub-builder Asset + `E_ASSET_HASH` | 媒体资产 sha256 + 源文件 source_sha256 |
| 每个 Segment 记 source_page（源页） | 我们已定 | Segment.meta.source_page + structured/raw/ 逐页产物 |

### D. 确定性

| 目标 | 经验来源 | 落点 |
|---|---|---|
| 同一冻结工作区两次构建字节一致 | epub-builder `TestBuildIsDeterministic` | 构建时间戳用冻结时间，不用 `time.Now()` |
| 结果按稳定原文序合并，不随并发完成顺序变 | epub-builder / wenyi 共识 | 并发合并按原文序 |

### E. 术语一致

| 目标 | 经验来源 | 落点 |
|---|---|---|
| GLOSSARY.csv 跨章/跨书一致 | 出版物规范 1.5「术语一致是跨书唯一保障」 | glossary 三态 + 冲突外置 |
| 术语类别（人物/地名/政党/组织/术语/事件/历史时期） | 出版物规范 GLOSSARY 类别 | glossary.csv 扩展 schema |
| 首现规则：政党缩写加全称、人物音译+原文 | 出版物规范 1.5 | 术语注入规则 |
| 新术语：子代理报告 → 主代理验证 → 入库 | 出版物规范 2.3 | 翻译 worker 只读+追加提案，单线程合并裁决 |
| 全流程统一替换 | `unify_terms.py` | build 前术语统一 |

### F. 翻译质量：审核优于生成

| 目标 | 经验来源 | 落点 |
|---|---|---|
| 子代理翻译、主代理审核写入（子代理不直接写文件） | 出版物规范「翻译最终质量取决于审核」 | 翻译 agent 返回、落盘由单线程合并器 |
| 理解日志（全书框架 + 逐章理解 + 翻译注意事项） | fleming `_理解日志.md` | `analysis/overview.md` + `units/` + `keypoints.md` |
| 反讽/语气/中立客观的情境化处理 | fleming 理解日志「英式反讽意译、政治中立」 | 文体档案 + 翻译指引 |
| 引用块双轨制（诗歌 `*...*` vs 引语 `>`） | 出版物规范 3.1 | 结构化引用块分类 |
| 书名号/标点规范（«»→《》、""→「」、嵌套「『』」） | 出版物规范 3.5 | 标点规范化纯函数 |

### G. 抽样审计 + 修复循环

| 目标 | 经验来源 | 落点 |
|---|---|---|
| 结构抽样 + 风险抽样 + 随机抽样 | fleming QA 报告（15/94 片，16%） | G1 审校抽样策略 |
| 高风险区必审（脚注/关键人物/复杂表格/OCR 存疑/引文） | fleming「B2-风险抽样」 | 审校 sampling 命中高风险单元 |
| 修复循环最多 3 轮后上报，不无限循环 | epub-builder「三次修复循环」 | G3 收敛状态机 max_rounds |

---

## 二、负面限制（必须避免）

### A. 内容丢失 / 重复 / 污染

| 禁止 | 实际案例 | 预防 |
|---|---|---|
| 孤立内容静默丢失 | epub-builder Phase 1 bug | 验证不变量：每 Block/Insert 必在 flow |
| 重复引用导致内容重复 | epub-builder `E_BLOCK_DUPLICATE_FLOW` | 去重校验 |
| 内容污染（多余段落混入相邻片） | fleming「删除多余的 0089 内容重复段落」 | 分片边界校验 |
| 插入元素内联处理破坏正文连贯性 | 出版物规范「插入元素是最强干扰源」 | 先提取、单独处理、再回插 |
| 段落间缺空行粘连成大段 | morris R1「276 段 + 275 空行」 | G0 空行/段落边界校验 |

### B. 术语 / 专名 / 称谓错误

| 禁止 | 实际案例 | 预防 |
|---|---|---|
| 人名用字错误 | 韩复渠→韩复榘 | G2 取证（人名/译名表）+ 术语命中 |
| 作品/杂志名误译 | 《生活与信笺》→《生活与文学》 | G1 术语/专名审校 |
| 冠名/军衔遗漏 | 近卫步兵团→近卫掷弹兵团 | G1 missing 类型 |
| 称谓不当 | 高级郡长→名誉郡长 | G1 术语/称谓 |
| 代词误用 | 对它们的控制→对他们的控制 | G1 pronoun 类型 |
| 介词/措辞不当 | M 和我的被邀请→M 和我被邀请 | G1 mistranslation |

### C. 结构破坏（机翻评测不关注的维度）

| 禁止 | 实际案例 | 预防 |
|---|---|---|
| 粗体配对不完整 | 出版物规范 qc_check | G0 标记配对纯函数 |
| 图片路径残留 / HTML 残留 / InDesign 残留 | 出版物规范 qc_check | G0 残留产物检查 |
| 跨分片断句 | 出版物规范 merge 修复 | G0 句边界 + merge 修复 |
| 有序列表渲染成 ul | epub-builder Phase 1 | G4 渲染审计 |
| 列表标记剥离丢失数字开头内容 | epub-builder Phase 1 | G4 渲染审计 |
| 孤字成行 / 页首孤字 | 传统校对规范 | G4 视觉抽审 |
| 脚注/尾注丢（学术书高发区） | pdf2epub / 出版物规范 | 脚注专项 + G4 双向跳转 |

### D. 非确定性 / 身份泄漏

| 禁止 | 实际案例 | 预防 |
|---|---|---|
| 构建时间戳用 `time.Now()` 导致非确定 | epub-builder `dcterms:modified` | 用冻结时间戳 |
| 内部 ID 暴露到产物（`footnote-1` 而非 `1`） | epub-builder Phase 5 | 确定性序号，内部 ID 不外泄 |
| 绝对路径/用户路径写入产物 | epub-builder「Environment Neutrality」 | 环境中立，不写 `/home/*` |

### E. 安全

| 禁止 | 实际案例 | 预防 |
|---|---|---|
| URL 注入（`javascript:`/`data:`） | epub-builder Phase 1 | G4 URL 安全校验 |
| 密钥/私密材料提交 | AGENTS 约定 | `.gitignore` + 环境变量读密钥 |

### F. 术语不一致（最隐蔽的质量问题）

| 禁止 | 实际案例 | 预防 |
|---|---|---|
| 跨章/跨书术语不一致 | 出版物规范「最隐蔽」 | glossary 三态 + 冲突仲裁 + 跨书术语缓存 |
| 同一词多种译法并存 | 赤区/苏区混用 | 术语冲突外置 + 人工裁决 |

### G. 源文质量陷阱

| 禁止 | 实际案例 | 预防 |
|---|---|---|
| OCR 粘连/乱码未清洗 | 西语 `delos`→`de los`、葡语 Mojibake | 清洗纯函数 + 逐页降级重做 |
| 源文排印讹误照抄 | "IDG"→IDF、"19487"→1948、年份粘连 | 源文勘误记录 + 按先例处理 |
| 日语纪年/敬语未处理 | 昭和→西历、敬语标准化 | langprofile 语言指引 |

---

## 三、映射到我们的 QC 六道关

| 关卡 | 承接的正向目标 / 负面限制 |
|---|---|
| G0 零 token 校验 | 标记守恒、段落 1:1、h1/h2 层级、粗体配对、图片路径/HTML/InDesign 残留、跨片断句、空行粘连、脚注配对、术语命中、标点规范、URL 安全 |
| G1 逐批审校 | 漏译/增译/误译/术语违例/代词——覆盖韩复榘、杂志名、冠名、称谓、介词措辞类错误；结构+风险+随机抽样 |
| G2 证据取证 | 人名/译名/术语裁决（韩复渠 vs 韩复榘）、源文勘误证据 |
| G3 仲裁+影子修订+盲复审 | 术语冲突（赤区/苏区）、跨章称谓统一、修复循环 max_rounds |
| G4 EPUB 结构 QA | epub:type、lang/xml:lang、landmarks、NCX/OPF、有序列表/列表标记、脚注确定性序号+双向跳转、原图优先+补充层、URL 安全 |
| G5 交付验收 | release 四必需组件（封面/元数据/正文/导航）、差错率、术语统一完成 |

## 四、三条贯穿原则（历史经验的最强共识）

1. **原始内容不可变，AI 识别是可追溯补充层**——原图优先、补充层不覆盖原件、确定性组织与验证。
2. **审核优于生成**——子代理/worker 只翻译不落盘，主代理/合并器审核后写入；生成不是质量来源，审核才是。
3. **分离关注点**——元数据/前置/正文/后置/术语/工程六层独立，插入元素与正文流分离，物理分片与逻辑结构经映射表连接；任一层可独立修改不影响其余。
