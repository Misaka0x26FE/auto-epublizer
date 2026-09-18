<!-- i18n: source=publishing-workflow.zh.md sha256=2e099466edac12790cf57528c167acbd72c389514d3499fa92dcba57df458e5b -->
> **English** | [中文](publishing-workflow.zh.md)

# Traditional Editorial and Publishing Workflow Reference

This document organizes the editorial workflow of traditional book publishing and translation
publishing (centered on the "three reviews and three proofreads") as a reference for the design of
auto-epublizer's editing/review/proofreading stages. Sources: CY/T 172—2019 "Academic Publishing
Specification: Book Publishing Process Management", the 1998 Press and Publication Administration
"Basic Regulations for Book Editing Work", CY/T 123—2015 "Academic Publishing Specification: Chinese
Translated Works", T/TAC 1—2016 "Specification for Translation Services".

## I. Overall publishing workflow

The editing stages defined by the "Basic Regulations for Book Editing Work" (in order):

```text
information → topic selection → soliciting manuscripts → manuscript review → processing and arrangement → overall design → submission → proofreading → quality inspection
      → publicity → review and introduction → editorial affairs
```

The core directly related to content quality is: **manuscript review (three reviews) → editing and processing → proofreading (three proofreads and one read) → quality inspection**.

## II. Three-review system (manuscript review)

Three-level manuscript review, with roles and duties progressing level by level:

| Review level | Holder | Main duties |
|---|---|---|
| First review | Responsible editor (intermediate professional title or above) | Read the whole manuscript, eliminate basic errors: typos, punctuation, faulty sentences, style (numerals/capitalization), normalization of translated names, figure/table placement, political and knowledge errors; write the first-review report; may return for revision/reject |
| Second review | Editorial office director (associate editor or above) | Eliminate problems the first review "was unsure about" and missed basic errors; standardize the whole-book architecture (heading levels, chapter/paragraph division, TOC levels, footnotes/endnotes, chapter logic); write the second-review report |
| Final review | President/editor-in-chief (full/deputy editor) | Resolve doubts left by the first and second reviews; assess whether the second review's planning is reasonable; political sensitivity and macro-level gatekeeping; may send back to first/second review |

Key rules:

- **No two stages may be held by the same person** (role separation, preventing reading paralysis and entrenched positions).
- **The right to return for revision belongs to the three reviews**: a manuscript revised by the author must be re-reviewed until it passes.
- The "first three reviews" (topic/manuscript-value gatekeeping) and the "last three reviews" (the three-level review of editing and processing) are two levels.
- Manuscript review is the judgement "on the accepted manuscript", editing and processing is the arrangement "after acceptance"; the two should not be confused (editing in place of review, or reviewing in place of editing, are both irregular).

## III. Editing and processing

- Prerequisite: only after the three reviews pass and adoption is decided does editing and processing begin.
- Content: all-round review + revision and polish + normalization processing (annotations, quotations, translated works, tables, illustrations follow the corresponding specifications).
- **An editing plan must first be formulated**: understand the whole book's writing style and textual quality, unify standards, avoid inconsistency before and after.
- Difficult problems are recorded in the editing-and-processing report, submitted to the second and final reviews for judgement and resolution.
- Use pens of different colours to distinguish manuscript-review opinions from editing-and-processing opinions, so that there is a record to check.

## IV. Proofreading (three proofreads and one read)

- Definition: **check the proofs against the manuscript (or definitive text) and correct errors on the proofs**.
- The core function has two layers:
  - **Checking similarities and differences**: against the manuscript, eliminate errors produced by typesetting/input/revision (faithful to the manuscript);
  - **Checking right and wrong**: discover as far as possible the omissions and errors remaining in the manuscript, **submit them to the editor for verification**; the proofreader has no independent authority to dispose.
- The three proofreads are carried out by **three different proofreaders in rotation**, to prevent paralysis after multiple readings.
- Proofreader operating conventions: use red pen for indisputable hard errors; use pencil for those based on judgement, deemed inappropriate in content, and after confirmation by the responsible editor/planning editor, mark with red pen.
- **Checking red (comparing red)**: check whether the previous proofreading round's changes were made in place, made wrongly, or missed.
- Three proofreads and one read: the responsible proofreader completes the textual-technical arrangement + a full read before printing.
- Common proofreading checkpoints: CIP and copyright page, TOC and body text word-for-word consistency, fonts/sizes/arrangement of heading levels unified throughout the book, figure/table placement, single-character lines, page numbers and running heads, etc.

## V. Translation publishing workflow (translated works)

Stages defined by the T/TAC 1—2016 translation service standard (in order):

```text
pre-translation preparation → translation → check → bilingual revision
        → monolingual review → proofread → verification and delivery
```

Terminology definitions:

- **check**: the translator checks their own translation.
- **bilingual revision**: a **comparative check** of the target language and the source language (synonymous with "bilingual editor").
- **monolingual review**: a **monolingual check** of the target language only (synonymous with "monolingual editor").
- **proofread**: check and correct the reviewed target-language content before printing.

Industry experience for translation books (Yilin Press's "four respects" + key points for editing and proofreading imported books):

1. **Trial translation system**: before formal translation, select 2–3 translators to trial-translate typical chapters for comparison and selection.
2. **Glossary first**: in the early stage of the translation, the translator produces a professional terminology list, for editing and proofreading reference, unified throughout the book.
3. **Unified translated names**: personal names and place names according to transliteration norms and established usage; append the original on first occurrence, add the full form as a note on first occurrence of abbreviations.
4. **Review and verification**: focus on checking omissions and mistranslations; for multi-translator works, focus on checking style consistency and contextual transitions.
5. **Respect the text**: do not delete or alter the original work's quotations, annotations, references, index; add edge indices to indexed works.
6. **Respect the translator**: do not arbitrarily change the translator's rendering of keywords; send proofs to the translator for inspection.

## VI. Mapping to auto-epublizer

> **Scope boundary**: auto-epublizer is only responsible for **delivery quality** — accuracy, completeness,
> consistency, compliance, structural correctness, reproducibility. It **makes no value/political/ideological
> judgements about the content**. The political gatekeeping and ideological gatekeeping of the traditional
> "final review" are outside this project's responsibility; the correspondences in the table below take only
> the **mechanism** of "overall-consistency final arbitration", not its value judgements.

Every quality stage of the traditional workflow can find a correspondence in our pipeline, and on that basis we have **strengthened** role separation and evidence-drivenness:

| Traditional stage | Requirement/duty | auto-epublizer correspondence |
|---|---|---|
| Manuscript receipt (complete, clear, final) | Body + front/back matter + figures/tables complete | `init`/ingest: source → structured four-layer structure |
| Understand the whole book, formulate an editing plan | Unify standards to prevent inconsistency | `analyze`: overview/global/units/keypoints generated and injected into translation |
| Glossary first | Translator builds a glossary in the early stage | agent seeds glossary three states + `references/` import |
| Trial translation system | 2–3 translators trial-translate for comparison | optional sample-chapter trial translation to verify quality (exploration stage) |
| First review | Eliminate basic errors (typos/punctuation/style/translated names) | QA gate 0 (zero-token deterministic checks) + gate 1 per-batch review (cheap) |
| Second review | Architecture + consistency + doubts | gate 2 evidence-gathering Agent Loop + gate 3 conflict arbitration |
| Final review (consistency final arbitration) | Overall consistency and macro-level gatekeeping (**no value judgements**) | gate 3 blind re-review + final arbitration |
| Editing and processing | Change only the accepted manuscript, keep records, report difficulties upward | shadow revision: shadow translation read-only, traces retained, only Autofix can change the official text |
| Checking similarities and differences | Against the manuscript, check only consistency | gate 0 alignment completeness + `align/` sentence-level validation |
| Checking right and wrong | Discover omissions and submit them to the editor for confirmation | review Agent reports issues (better to omit than to over-flag), does not directly change |
| Checking red (comparing red) | Check changes in place/wrong/missed | blind re-review after shadow revision + oscillation detection (digest SHA-256) |
| Three proofreads and one read | Multiple rounds by different people + responsible proofreader's full read | consecutive clean confirmations + final QA (epubcheck zero errors) |
| Unified translated names | Established usage + transliteration norms | glossary + references unification + conflict arbitration |
| Printing/final proof | Complete, clear, final, go to print | `build` + `qa` |

### Three key design principles brought by the traditional workflow (already absorbed)

1. **Role separation**: no two review levels may be the same person → our review Agent is separate from the translation Agent and the Fixer, and blind re-review does not pass on the old explanation.
2. **Layered checking of similarities/differences vs right/wrong**: deterministic checks (zero-token, alignment, pure functions) are separated from judgemental checks (review Agent) — the former blocks one line first without spending tokens.
3. **Proofreaders have no independent authority to dispose**: doubts found are marked in pencil, not directly changed → our review only reports issues, revision goes through the shadow overlay, and the official translation is updated only by an explicit Autofix.
