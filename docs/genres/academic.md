<!-- i18n: source=academic.zh.md sha256=722b3ce94ca9703a8d9f4a0c42fcd86ee83f3e48291a43b7f1ab2b565cfdf781 -->
> **English** | [中文](academic.zh.md)

# Academic Monograph · Translation Optimization Document

> The dedicated optimization specification for academic monographs. Academic books have the
> most complete structure and depend heavily on "searchable, verifiable, reproducible"
> knowledge-organizing supplementary matter.

## 1. Genre Positioning and Identification Features

An academic monograph **completes the searchable and referential supplementary matter** on
top of the "general book structure"; it is the book type with the most complete structure.

Identification features:

- Has introduction/prolegomena, parts/chapters/sections, footnotes/endnotes, references, index, appendix, explanatory notes;
- The body contains footnotes, charts and citations;
- Serves "searchable, verifiable, reproducible" rather than narration.

## 2. Structural Features and Frontmatter/Backmatter Focus

| Region | Handling |
|---|---|
| Cover/spine/back cover | Content summary, ISBN barcode; author bio on the foldout |
| Title page/copyright page | Contains CIP data, metadata cataloguing |
| Content summary | Needs translation, introductory supplementary matter |
| Preface/foreword/explanatory notes | Need translation; explanatory notes (common in reference works/compilations) need understanding |
| Table of contents | Search-oriented supplementary matter, hierarchy must match the body |
| Body | Parts/chapters/sections + footnotes + charts + citations |
| Appendix/notes (endnotes)/references/index | **Lifeline**, must never be lost, index gets edge codes |
| Afterword/postscript | Needs translation |

## 3. Analysis Dimensions (consulted by the agent when writing analysis/)

| Field | Meaning |
|---|---|
| `discipline` | Discipline/field |
| `terminology` | Terminology system (including conventional translation-name conventions) |
| `argument` | Argument structure / central thesis |
| `citation_style` | Citation/note/reference format (author-year / footnote style) |
| `register` | Register (formal academic) |

## 4. Terminology and Entity Table

| Type | Description | Handling |
|---|---|---|
| `学科术语` term | Core concepts of the field | Strictly consistent throughout the book, checked against conventional translation names |
| `专名` proper | Personal names/place names/organizations | Checked against the `references/` translation-name table |
| `缩略语` abbreviation | Institution/committee/term abbreviations | Annotate the full name at first occurrence |

The glossary's type whitelist switches to discipline terms along with the genre, avoiding
novel-style appellation/verbal-tic extraction.

## 5. Translation Guidance

1. Terminology strictly consistent throughout the book, using domestically conventional translation names (refer to the official translation-name tables in `references/`, e.g. the Commercial Press's *A Handbook of English Name Translations*);
2. Long sentences restructured and split by logic; passive voice and nominalization converted per Chinese academic conventions;
3. Preserve citations, notes, references and the index; **index gets edge codes** for easy retrieval;
4. Numbers and units of measurement unified (Anglo-American system converted to International System); abbreviations annotated with the full name at first occurrence;
5. References: English journal/book titles in italics, format unified, **not translated**.

## 6. Review Focus (Mapping to QC)

| QC gate | Academic focus |
|---|---|
| G0 | Terminology hits (discipline terms strictly matched), number units, abbreviation annotation |
| G1 | Focus on `terminology` (terminology violations), `missing` (omitted citations/notes/index) |
| G2 | Evidence: glossary + sources of conventional translation names (references) |
| G3 | Conflict arbitration focuses on cross-chapter consistency of discipline terms |

**Strictness**: inconsistent terminology, omitted citations and lost notes in academic books
are hard defects, and review tolerance is low (compared with novels).

## 7. Special Optimization Checklist

- [ ] Discipline-term whitelist + conventional translation-name cross-reference (references)
- [ ] Index edge codes preserved
- [ ] Abbreviations annotated with full name at first occurrence
- [ ] Reference format unified and untranslated
- [ ] Numbers/units of measurement normalized
- [ ] Footnotes/endnotes bidirectional jumps (EPUB rebuilding)
- [ ] Review terminology + missing weighting + low tolerance
