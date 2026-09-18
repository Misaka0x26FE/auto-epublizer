<!-- i18n: source=paper.zh.md sha256=39c2df2179862a289fbbca3826aaabd0356f9d78323f8e8c6ddebd9481953e1c -->
> **English** | [中文](paper.zh.md)

# Paper (IMRaD) · Translation Optimization Document

> The dedicated optimization specification for journal articles/academic papers. Papers do
> not adopt the book's "binding + preface/postscript" system; they follow the internationally
> standard IMRaD structure.

## 1. Genre Positioning and Identification Features

Identification features:

- Frontmatter: title → authors and affiliations → abstract → keywords (3–5);
- Body: introduction → methods → results → discussion → conclusion (IMRaD);
- Backmatter: acknowledgements/funding → references → appendix → supplementary materials/conflict-of-interest statement/author-contribution statement;
- Metadata is DOI, volume/issue/page numbers (not ISBN/CIP).

## 2. Structural Features and Frontmatter/Backmatter Focus

| Region | Handling |
|---|---|
| Title/authors/affiliations | Metadata cataloguing, author names per conventional translation names |
| Abstract | Needs translation, structured abstracts keep their structure |
| Keywords | Needs translation, terminology unified |
| Introduction/methods/results/discussion/conclusion | The main battlefield of translation |
| References | Format unified, **not translated** |
| Acknowledgements/funding | Needs translation |

## 3. Analysis Dimensions (consulted by the agent when writing analysis/)

| Field | Meaning |
|---|---|
| `research_question` | Research question / gap |
| `method` | Research method and design |
| `findings` | Core findings |
| `conclusion` | Conclusions and limitations |

## 4. Terminology and Entity Table

| Type | Description | Handling |
|---|---|---|
| `领域术语` term | Core concepts of the discipline | Strictly consistent throughout the book |
| `缩略语` abbreviation | Institution/method/term abbreviations | Annotate the full name at first occurrence |

## 5. Translation Guidance

1. **Separate results and discussion**: results objectively present data and offer no interpretation; only the discussion interprets meaning (reproducibility principle);
2. Terminology strictly unified; abbreviations annotated with the full name at first occurrence;
3. Data and figure/table captions standardized; statistical descriptions objectively relayed.

## 6. Review Focus (Mapping to QC)

| QC gate | Paper focus |
|---|---|
| G0 | Terminology hits, abbreviation annotation |
| G1 | Focus on `terminology`, results/discussion boundary (`mistranslation`) |
| G2 | Evidence: glossary + discipline-standard sources |
| G3 | Cross-paragraph terminology consistency |

## 7. Special Optimization Checklist

- [ ] IMRaD structure preserved (introduction/methods/results/discussion/conclusion not mixed)
- [ ] Results/discussion separated, data objective
- [ ] Terminology unified + abbreviations annotated with the full name at first occurrence
- [ ] References untranslated + format unified
- [ ] Abstract/keywords terminology consistency
