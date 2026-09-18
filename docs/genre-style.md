<!-- i18n: source=genre-style.zh.md sha256=e3fb9cf30873fff9a55367a9a5b925e1e833d90364e3c4e291331b042a8defac -->
> **English** | [中文](genre-style.zh.md)

# Genre Style Optimization (Overview and Index)

Different genres place very different demands on analysis, translation, terminology and
review. This directory provides one dedicated document per genre; this document is the
overview and index.

## Core Framework: Two Orthogonal Dimensions

```text
genre profile (varies by genre)  ×  language-specific guidance (langprofile, varies by source language)
```

- **Genre profile** determines: analysis dimensions (what analyze extracts), the
  terminology-type whitelist (which words to extract), translation guidance (how to
  translate), review focus (what a reviewer counts as a problem), and frontmatter/backmatter
  focus (which supplementary matter matters).
- **Language guidance** determines: language pitfalls during translation (honorifics,
  gendered pronouns, tense, onomatopoeia, Han-character words…), independent of genre.

The two overlay to form the genre guidance injected into the prompt. The genre profile is
**declarative data**, loaded by the `genre` key; adding a genre does not require code
changes.

## Genre Document Index

| Genre | Document | Core special optimizations |
|---|---|---|
| Novel narrative | [novel.md](genres/novel.md) | Character bible + source-only terms + honorific strategy + dialogue distinctiveness + rolling previous-context linkage |
| Academic monograph | [academic.md](genres/academic.md) | Discipline terminology consistency + index edge codes + abbreviation annotation + references untranslated + number/unit conventions |
| Paper (IMRaD) | [paper.md](genres/paper.md) | IMRaD structure + results/discussion separation + abbreviation annotation + reproducibility |
| Poetry/prose | [poetry.md](genres/poetry.md) | Line-structure preservation + imagery first + rhyme-scheme declaration |
| Newspaper/periodical | [newspaper.md](genres/newspaper.md) | Organization by page layout + headline-to-lead conversion + factual/quote accuracy + objective relay |

## Language-Specific Guidance (langprofile, independent of genre)

| Source language | Key points |
|---|---|
| `ja` | Honorific strategy; first person (私/僕/俺/あたし) domains and pronouns; onomatopoeia/mimetic words follow Chinese conventions; Han-character words ≠ Chinese words, do not copy directly; furigana 〘〙 for interpretation only, strictly forbidden to write in |
| `en` | No honorifics, Mr./Ms./Sir consistent throughout; decide "he/she/it" from name gender and context; tense/relative clauses/long sentences restructured per Chinese, passive to active as appropriate; proper-noun transliteration |
| `ru/ko/fr/de/es…` | Faithful conveyance of meaning, conforming to Chinese target-language expression conventions |

## Unified Genre Profile Schema

`publication.json.meta.genre` declares/determines the genre; `analysis/style.md` stores
the genre profile:

```yaml
genre: novel                # novel | academic | paper | poetry | newspaper | ...
detect: auto                # auto | explicit declaration
style: { … }                # genre analysis dimensions
characters: […]             # novel: character bible
term_types: […]             # terminology-type whitelist for this genre
review_focus: […]           # review issue-type weighting
translation_rules: […]      # genre translation guidance
```

## Injection Order (Following "Static → Dynamic")

The system prompt holds genre guidance + language guidance + punctuation rules; the user
prompt holds style/character bible → book overview → chapter synopsis → key points →
terminology subset → previous translation → text to translate.
