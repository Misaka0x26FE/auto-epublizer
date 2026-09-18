<!-- i18n: source=quality-lessons.zh.md sha256=52c015f7aa58a4f6fbcb0611e7fa6d25f57c9f2d3328c8ea3d53f2bde39cc3c6 -->
> **English** | [中文](quality-lessons.zh.md)

# Quality-Control Measures (Distilled from Historical Practice)

> **Positioning**: this file is the **specification table** (positive goals / negative
> constraints) and serves as the design basis for the six QC gates.
> **Situation-specific field experience** (criterion / handling / verification) is in
> `skills/auto-epublizer/lessons/` (one topic per file, e.g. scanned matter / MinerU /
> translation workflow) — the two are complementary: the specification table sets the
> standard, lessons offer "how to judge and fix when meeting a specific source site /
> dirty source / edge case".
> **Sources**: see the two historical work products below.

Distilled from two historical work products, as the **positive goals** (must achieve) and
**negative constraints** (must avoid) of auto-epublizer quality control.

Sources:
- `~/work/translate/` —— full-pipeline translation experience from 11 publications (`出版物结构与处理规范.md`,
  each book's `_理解日志.md`, `QA报告.md`, `qa_findings.md`, `GLOSSARY.csv`);
- `~/github/epub-builder` —— a Go-implemented EPUB organization/build/validation CLI (`PROGRESS.md`,
  `specification.md`, `qa.md`, `review.md`), iterated to a release gate.

---

## 1. Positive Goals (Must Achieve)

### A. Content integrity: no loss, no duplication

| Goal | Source of experience | Landing point |
|---|---|---|
| Reject orphaned content (a Block not in any flow) | epub-builder `E_BLOCK_NOT_IN_FLOW` | G0/G4 structural audit: every unit must be in the content tree |
| Reject duplicate references (duplicates within a flow, duplicates across flows) | `E_DUPLICATE_FLOW_REF` | content-tree validation invariant |
| "If a source exists it must be included" (SourceCatalog inventory) | epub-builder SourceCatalog | register the source inventory when splitting `structured/`; validate full coverage |
| Conservation of inserts marker count (`{fig:NNN}` 32/32) | morris qa_findings "marker count conservation" | G0 alignment-table/marker conservation check |
| Footnote note-reference conservation (1:1) | morris "note reference conservation", fleming footnote sampling | G0 footnote reference ↔ definition pairing |
| Paragraph block count 1:1 (reasonable differences from merging page-break fragments allowed) | morris "paragraph block count 16/21 exactly 1:1" | G0 sentence/paragraph count consistency |
| h1/h2 hierarchy count consistent with the source | morris "h1/h2 hierarchy count consistent" | G0 heading hierarchy validation |

### B. Correct structure

| Goal | Source of experience | Landing point |
|---|---|---|
| Staged validation structure → freeze → release | epub-builder three-stage gate | the `qa` command is staged; the release gate blocks release |
| release's four required components (cover/metadata/body/navigation) | epub-builder `E_REQUIRED_*` | G4/G5 release conditions |
| Stable ID (canonical address, not filename/line number/page number) | epub-builder Node/Block/Insert ID | our unit stable ID |
| epub:type semantics (frontmatter/bodymatter/backmatter/bibliography/index/appendix) | epub-builder Phase 6 | four-layer structure → epub:type mapping |
| Correct lang/xml:lang, landmarks nav, NCX/OPF metadata | epub-builder Phase 6 | G4 EPUB audit items |
| TOC mapping table (hierarchy / original title / Chinese title / original page number / PDF page number) | publication spec 1.2 | TOC mapping in `analysis/` or publication.json |
| Chapter type classification (narrative/argumentative/mixed/reference) | publication spec 1.3 | annotate chapter type in `analysis/units/`, driving translation strategy |

### C. Traceable

| Goal | Source of experience | Landing point |
|---|---|---|
| Original image first, AI recognition is a supplementary layer (`<details>`), does not overwrite the original | epub-builder "original image first + Supplement" | tables/formulas/illustrations: original image + recognition supplement layer |
| Dual positioning for notes (absolute position + relative position) | epub-builder NoteRecord dual positioning | footnotes: absolute position of the source page + relative position of the body anchor |
| Deterministic numbering (1,2,3 rather than internal ID) | epub-builder "deterministic numbering" | footnote/endnote numbering restarts at 1 per chapter |
| Asset SHA-256 binding, content hash verification | epub-builder Asset + `E_ASSET_HASH` | media asset sha256 + source file source_sha256 |
| Each Segment records source_page (source page) | already decided by us | Segment.meta.source_page + per-page artifacts in structured/raw/ |

### D. Determinism

| Goal | Source of experience | Landing point |
|---|---|---|
| Two builds of the same frozen workspace are byte-identical | epub-builder `TestBuildIsDeterministic` | build timestamps use the frozen time, not `time.Now()` |
| Results merged in stable source order, not varying with concurrent completion order | epub-builder / wenyi consensus | concurrent merge in source order |

### E. Terminology consistency

| Goal | Source of experience | Landing point |
|---|---|---|
| GLOSSARY.csv consistent across chapters/books | publication spec 1.5 "terminology consistency is the only cross-book guarantee" | glossary three states + conflict externalization |
| Terminology categories (person/place/political party/organization/term/event/historical period) | publication spec GLOSSARY categories | glossary.csv extended schema |
| First-occurrence rule: party abbreviations get the full name, person names get transliteration + original text | publication spec 1.5 | terminology injection rules |
| New terms: sub-agent reports → main agent verifies → enter the store | publication spec 2.3 | translation workers are read-only + append proposals; single-threaded merger arbitrates |
| Unified replacement across the whole pipeline | `unify_terms.py` | terminology unification before build |

### F. Translation quality: review over generation

| Goal | Source of experience | Landing point |
|---|---|---|
| Sub-agents translate, main agent reviews and writes (sub-agents do not write files directly) | publication spec "final translation quality depends on review" | translation agent returns; persistence by a single-threaded merger |
| Understanding log (whole-book framework + per-chapter understanding + translation notes) | fleming `_理解日志.md` | `analysis/overview.md` + `units/` + `keypoints.md` |
| Contextual handling of irony/tone/neutral objectivity | fleming understanding log "British irony paraphrased, political neutrality" | genre profile + translation guidelines |
| Dual-track block quotes (poetry `*...*` vs quotations `>`) | publication spec 3.1 | structured block-quote classification |
| Book-title marks / punctuation norms («»→《》, ""→「」, nested 「『』」) | publication spec 3.5 | punctuation normalization pure function |

### G. Sampling audit + repair loop

| Goal | Source of experience | Landing point |
|---|---|---|
| Structural sampling + risk sampling + random sampling | fleming QA report (15/94 pieces, 16%) | G1 review sampling strategy |
| High-risk areas must be reviewed (footnotes/key persons/complex tables/OCR doubts/quotes) | fleming "B2 - risk sampling" | review sampling hits high-risk units |
| Repair loop reports upward after at most 3 rounds, no infinite loop | epub-builder "three repair loops" | G3 convergence state machine max_rounds |

---

## 2. Negative Constraints (Must Avoid)

### A. Content loss / duplication / contamination

| Forbidden | Actual case | Prevention |
|---|---|---|
| Silent loss of orphaned content | epub-builder Phase 1 bug | validation invariant: every Block/Insert must be in a flow |
| Duplicate references causing content duplication | epub-builder `E_BLOCK_DUPLICATE_FLOW` | deduplication check |
| Content contamination (extra paragraphs mixed into adjacent pieces) | fleming "delete the extra duplicated 0089 content paragraph" | fragment boundary check |
| Inline handling of inserts breaking body continuity | publication spec "inserts are the strongest source of interference" | extract first, handle separately, then re-insert |
| Missing blank lines between paragraphs gluing them into one big paragraph | morris R1 "276 paragraphs + 275 blank lines" | G0 blank-line/paragraph boundary check |

### B. Terminology / proper-noun / appellation errors

| Forbidden | Actual case | Prevention |
|---|---|---|
| Wrong character in a person's name | 韩复渠→韩复榘 | G2 evidence-gathering (person-name/translation-name table) + terminology hit |
| Mistranslation of a work/magazine name | 《生活与信笺》→《生活与文学》 | G1 terminology/proper-noun review |
| Omission of a title/military rank | 近卫步兵团→近卫掷弹兵团 | G1 missing type |
| Inappropriate appellation | 高级郡长→名誉郡长 | G1 terminology/appellation |
| Misuse of pronouns | 对它们的控制→对他们的控制 | G1 pronoun type |
| Inappropriate preposition/wording | M 和我的被邀请→M 和我被邀请 | G1 mistranslation |

### C. Structural damage (dimensions machine-translation evaluation does not care about)

| Forbidden | Actual case | Prevention |
|---|---|---|
| Incomplete bold pairing | publication spec qc_check | G0 marker-pairing pure function |
| Image path residue / HTML residue / InDesign residue | publication spec qc_check | G0 residue artifact check |
| Sentence split across fragments | publication spec merge repair | G0 sentence boundary + merge repair |
| Ordered list rendered as ul | epub-builder Phase 1 | G4 rendering audit |
| Stripping of list markers losing content that starts with a number | epub-builder Phase 1 | G4 rendering audit |
| Single character on a line / orphan at the top of a page | traditional proofreading norms | G4 visual sampling |
| Lost footnotes/endnotes (a high-incidence area in academic books) | pdf2epub / publication spec | dedicated footnote work + G4 bidirectional jumps |

### D. Non-determinism / identity leakage

| Forbidden | Actual case | Prevention |
|---|---|---|
| Build timestamp using `time.Now()` causing non-determinism | epub-builder `dcterms:modified` | use a frozen timestamp |
| Internal ID exposed in the product (`footnote-1` instead of `1`) | epub-builder Phase 5 | deterministic numbering, internal IDs not leaked |
| Absolute paths / user paths written into the product | epub-builder "Environment Neutrality" | environment neutrality, do not write `/home/*` |

### E. Security

| Forbidden | Actual case | Prevention |
|---|---|---|
| URL injection (`javascript:`/`data:`) | epub-builder Phase 1 | G4 URL security validation |
| Committing keys/private material | AGENTS convention | `.gitignore` + reading keys from environment variables |

### F. Terminology inconsistency (the most insidious quality problem)

| Forbidden | Actual case | Prevention |
|---|---|---|
| Cross-chapter/cross-book terminology inconsistency | publication spec "most insidious" | glossary three states + conflict arbitration + cross-book terminology cache |
| Multiple translations of the same word coexisting | 赤区/苏区 mixed usage | terminology conflict externalization + human arbitration |

### G. Source-quality traps

| Forbidden | Actual case | Prevention |
|---|---|---|
| OCR gluing/garbling not cleaned | Spanish `delos`→`de los`, Portuguese Mojibake | cleaning pure function + per-page degraded redo |
| Copying source typographic errors | "IDG"→IDF, "19487"→1948, year gluing | source errata record + handling by precedent |
| Japanese era names/honorifics not handled | 昭和→Western calendar, honorific standardization | langprofile language guidance |

---

## 3. Mapping to Our Six QC Gates

| Gate | Positive goals / negative constraints undertaken |
|---|---|
| G0 zero-token validation | marker conservation, paragraph 1:1, h1/h2 hierarchy, bold pairing, image-path/HTML/InDesign residue, cross-fragment sentence splitting, blank-line gluing, footnote pairing, terminology hits, punctuation norms, URL security |
| G1 per-batch review | omissions/additions/mistranslations/terminology violations/pronouns — covering 韩复榘, magazine names, titles, appellations, prepositional wording errors; structural + risk + random sampling |
| G2 evidence gathering | person-name/translation-name/terminology arbitration (韩复渠 vs 韩复榘), source-errata evidence |
| G3 arbitration + shadow revision + blind re-review | terminology conflicts (赤区/苏区), cross-chapter appellation unification, repair loop max_rounds |
| G4 EPUB structural QA | epub:type, lang/xml:lang, landmarks, NCX/OPF, ordered lists/list markers, footnote deterministic numbering + bidirectional jumps, original image first + supplement layer, URL security |
| G5 delivery acceptance | release's four required components (cover/metadata/body/navigation), error rate, terminology unification complete |

## 4. Three Cross-Cutting Principles (the strongest consensus of historical experience)

1. **Original content is immutable; AI recognition is a traceable supplement layer** — original image first, the supplement layer does not overwrite the original, deterministic organization and validation.
2. **Review over generation** — sub-agents/workers only translate and do not persist; the main agent/merger reviews before writing; generation is not the source of quality, review is.
3. **Separation of concerns** — metadata/frontmatter/body/backmatter/terminology/engineering are six independent layers; inserts are separated from the body flow; physical fragments are connected to the logical structure via a mapping table; any layer can be modified independently without affecting the rest.
