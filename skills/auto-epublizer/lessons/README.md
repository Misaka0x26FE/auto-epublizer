<!-- i18n: source=README.zh.md sha256=8124b22066a33407f83d64cc44e948b0e20a84c405705cd7dd8f5a45bb5869fc -->
> **English** | [中文](README.zh.md)

# Lessons (distilled field experience)

This subdirectory holds **experience from real work (processing real books/source sites) for
specific situations**, as distinct from `references/` (routine operational guidance for each book).
Each lessons entry corresponds to one **specific source site/dirty source/edge case**, for
downstream agents to directly consult and handle when they encounter the same type of situation.

## Division of labour with references

| Directory | Answers | Trigger |
|---|---|---|
| `references/` | how to do each step for each book | read only one per stage (SKILL.md routing table) |
| `lessons/` | this special situation was encountered, how to judge, how to fix | read only when a **source site/dirty source/edge case** matches |

## Conventions (must-read before writing)

1. **Experience is "criterion + handling", not a conclusion**: you must clearly write "how to judge
   that this situation is hit" and "how to handle/verify", and not copy the final strings of a
   particular fix — the downstream agent adapts on its own per the criterion.
2. **One entry per topic**: named `YYYY-MM-DD-<topic>.md`, covering only one specific situation.
3. **Must include a "Reproduction/verification" section**: how to locally replay the situation (e.g. a
   minimal fixture), ensuring the experience is self-proving and not empty talk.
4. **Cite readable code locations**: when build/provenance and similar behaviour is involved, give
   `file:line`, and mark whether it is already fixed in the main repo (`已修复` or `see plans/xxx`).
5. **No user data in the entries**: no real book sources/translations/keys; fixtures are always
   tempfile or anonymized.

## Index

| Document | Topic | Status |
|---|---|---|
| [2026-09-05-baka-tsuki-html-figures.md](2026-09-05-baka-tsuki-html-figures.md) | Baka-Tsuki source-site HTML illustration paragraph structure (three lines figure>a>img) fidelity and restoration in ingest/build | fixed (1766e7a etc.) + experience retained |
| [2026-09-05-scanned-pdf-mineru-first.md](2026-09-05-scanned-pdf-mineru-first.md) | Scanned PDF: MinerU first priority (line-break/illustration recognition), traditional OCR recognizes only characters and needs the agent to read page by page as fallback | landed (ingest/mineru.py) + experience retained |
| [2026-09-05-scanned-pdf-operations.md](2026-09-05-scanned-pdf-operations.md) | Scanned-file operations: >200 pages batch/merge, **do not script the splitting (the agent splits manually)**, single-unit build loses nav, fenced code blocks lack support | experience retained (DouBao four-round measurement) |
| [2026-09-05-agent-translation-workflow.md](2026-09-05-agent-translation-workflow.md) | agent main-process translation workflow: build and verify every 3–5 units, finalize headings first, use the Write tool instead of heredoc, G0 warnings cannot all be treated as noise | experience retained (GT1/GT2/On Lisp measurement) |
| [2026-09-05-scanned-pdf-issue-checklist.md](2026-09-05-scanned-pdf-issue-checklist.md) | Scanned-file full-flow 15-issue checklist: main-repo gap verification (fenced code blocks/link regex/escaping) + epubcheck error code quick reference + fix suggestions | experience retained (JS authoritative guide measurement; gaps pending merge) |
| [2026-09-05-dogfooding-pdf-lessons.md](2026-09-05-dogfooding-pdf-lessons.md) | Real-book dogfooding 5 PDF pipeline defects: formula symbol set/font ratio guard/table double guard/qa jar configuration/OCR raw directory | fixed + experience retained (from plan §6 verification record) |
| [2026-09-06-conservation-total-only.md](2026-09-06-conservation-total-only.md) | Conservation-type G0 validation must do unit-level total comparison (line-level comparison produces false positives from split/merge sentences); source fidelity uses normalized concatenated substring matching | landed (review/g0.py + review/fidelity.py) |
| [2026-09-11-epub-nonlinear-spine-tables.md](2026-09-11-epub-nonlinear-spine-tables.md) | EPUB nonlinear spine items (tables) skipped by pandoc + heading anchor leftovers + frontmatter fragmentation → split by OPF spine and inline nonlinear items | fixed (ingest/epub_reader.py + test_epub_reader.py) |
| [2026-09-12-epub-internal-links-anchors.md](2026-09-12-epub-internal-links-anchors.md) | EPUB internal links/page anchors/heading id carrying pandoc source-file prefixes → rewrite by spine mapping to finished-product units (cross-unit links / same-unit pure anchors) | fixed (structure/links.py + build/html.py + ingest/epub_reader.py) |
| [2026-09-13-delivery-integrity.md](2026-09-13-delivery-integrity.md) | Tool QA all passes yet 38/72 images missing (translated body loses image paragraphs, conservation only checks align) → delivery audit independent reconciliation + rebuild with align + full re-verification | landed (qa/provenance.py reconciliation automation + references/delivery.md mandatory checklist) |

## Source and destination (how experience gets here)

- **DouBao four-round measurement** (GT1/GT2 HTML → On Lisp PDF → JS authoritative guide scanned file →
  MinerU redo): experience lands directly in `scanned-pdf-operations` / `agent-translation-workflow` /
  `scanned-pdf-issue-checklist`; the artifacts are on the Feishu cloud drive (A Certain Magical Index GT
  series / On Lisp / JavaScript authoritative guide folders).
- **Real-book dogfooding** (2026-09-04): the verification record in §6 of the plan
  `docs/plans/2026-09-04-pdf-dogfooding.md` is the experience source, deposited in this entry as a
  lesson; the plan document retains the verification context.
- **Main-repo fix status**: each entry's "Status" column marks whether it is fixed (`已修复` + commit
  hash); the unfixed ones (e.g. fenced code blocks) are clear follow-up development gaps.

> Convention: new experience always lands in `lessons/` (criterion/handling/verification three-part
> form); if a plan document's verification record contains reusable experience, after completion deposit
> a lessons entry in sync and cross-reference each other.
