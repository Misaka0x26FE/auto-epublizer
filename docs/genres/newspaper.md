<!-- i18n: source=newspaper.zh.md sha256=4555d1d165f61eea75eee965fd494db6cd9ebf18e32bb7889de823a990f1f4fb -->
> **English** | [中文](newspaper.zh.md)

# Newspaper and Periodical · Translation Optimization Document

> The dedicated optimization specification for newspapers/periodicals. Newspapers are
> organized by **page layout** rather than "preface/postscript + body", and are serial
> publications.

## 1. Genre Positioning and Identification Features

Identification features:

- **Newspaper**: masthead (paper name/publication number/postal issue code/date/total issue number), ear panel, running head, page layout, columns, lead story/second lead, double-page spread;
- **Content**: news (dispatches/reports/features) + opinion (editorials/commentary/editor's notes) + supplements (special pages) + advertisements;
- **Periodical**: between books and newspapers, with cover, contents page, columns, body articles; academic journals carry volume/issue numbers, ISSN, abstract, keywords, references.

## 2. Structural Features and Frontmatter/Backmatter Focus

| Region | Handling |
|---|---|
| Masthead/running head | Metadata cataloguing (paper name, date, publication number, page order) |
| Column/page attribution | **Preserved**, not broken up into chapters |
| Title | Needs translation, concise, lead placed first |
| Body (dispatches/editorials/commentary) | The main battlefield of translation |
| Advertisements (newspapers) | Usually skipped or marked |

## 3. Analysis Dimensions (consulted by the agent when writing analysis/)

| Field | Meaning |
|---|---|
| `layout` | Page layout structure / column attribution |
| `style` | News style (dispatch/report/editorial/commentary) |
| `periodicity` | Periodicity / timeliness |

## 4. Terminology and Entity Table

- Personal names/institutions/place names (checked against conventional translation names);
- Stance-expressing expressions in editorials/commentary are **objectively relayed** (not rewritten because of the opinion).

## 5. Translation Guidance

1. **Titles concise, lead placed first** (Chinese news convention);
2. **Preserve page layout/column attribution relationships**, not broken up into chapters;
3. The tone and stance of editorials/commentary are objectively relayed, not rewritten because of the opinion;
4. Dispatches follow the "inverted pyramid" structure, with key points placed first.

## 6. Review Focus (Mapping to QC)

| QC gate | Newspaper focus |
|---|---|
| G0 | Title/lead completeness, terminology hits |
| G1 | Focus on `mistranslation` (facts/numbers/quotes), `missing` (lead key points) |
| G2 | Evidence: conventional translation names for personal names and institutions |
| G3 | Cross-page consistency of personal names/institutions |

**Strictness**: news facts, numbers and quotes must be accurate (a high-incidence area for media errors); review focuses on facts and quotes.

## 7. Special Optimization Checklist

- [ ] Organized by page layout/column (not chapters)
- [ ] Headline-to-lead conversion + inverted-pyramid structure
- [ ] Facts/numbers/quotes accurate (a review focal point)
- [ ] Editorials/commentary objectively relayed
- [ ] Cross-page consistency of personal names/institutions
