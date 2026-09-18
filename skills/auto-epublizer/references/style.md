<!-- i18n: source=style.zh.md sha256=5fe9edc8cf052eac0bc1e406414b40c398036e0ac9108e6e264082587d463227 -->
> **English** | [中文](style.zh.md)

# Style (genre profile application)

Genre profile × language guidance (langprofile) are two orthogonal dimensions that determine the emphasis of analysis, translation, terminology and review.
The genre profile is declarative data, loaded by the `genre` key; adding a new genre does not change code.

## Genre index

| Genre | genre | Core special optimizations |
|---|---|---|
| Novel/narrative | `novel` | character bible + source-only terminology + honorific strategy + dialogue distinctiveness + rolling continuity with preceding text |
| Academic monograph | `academic` | discipline terminology consistency + index marginal numbers + abbreviation annotation + references untranslated + number/unit conventions |
| Paper | `paper` | IMRaD structure + separation of results/discussion + abbreviation annotation + reproducibility |
| Poetry/prose | `poetry` | line structure preservation + imagery priority + rhyme strategy declaration |
| Newspaper/periodical | `newspaper` | organization by page layout + headline-to-lead treatment + accurate facts/quotes + objective relay |

## Genre profile schema (`analysis/style.md`)

```yaml
genre: novel
detect: auto            # auto | explicit declaration
style: { ... }          # genre analysis dimensions
characters: […]         # novel: character bible
term_types: […]         # terminology type whitelist
review_focus: […]       # review issue type weighting
translation_rules: […]  # genre translation guidance
```

## Terminology type whitelist (switches with genre)

- Novel: `person/place/org/term/appellation/honorific/speech/fixed_expr`; appellations/speech tics are
  source-only category annotations (kept consistent during translation; the terminology hit check has no special branch).
- Academic: `term/person/place/org/event/work`, discipline terminology strictly matched + abbreviation annotation.
- Paper: `term/abbreviation`, abbreviation annotated at first occurrence.

## Language guidance (langprofile, independent of genre)

| Source language | Key points |
|---|---|
| `ja` | honorific strategy; first person (私/僕/俺/あたし) consistent across paragraphs; onomatopoeia/mimetic words per Chinese convention; kanji words ≠ Chinese words, do not copy verbatim |
| `en` | no honorifics, unify Mr./Ms./Sir; determine "he/she/it" by gender; restructure long sentences per Chinese, convert passive to active as appropriate; transliterate proper nouns |
| `ru/ko/fr/de/es…` | faithful conveyance of meaning, conforming to Chinese expression conventions |

## Context organization order (static → dynamic)

The context assembly order when the agent translates on its own (there is no prompt injection mechanism; everything is material you read into context):
genre guidance + language guidance + punctuation rules (static) → style/character bible → book overview → chapter summary →
key points → terminology subset → preceding translation → text to translate (dynamic, carried as needed).

## Review emphasis (mapped to QC)

| Genre | G0 emphasis | G1 emphasis |
|---|---|---|
| Novel | sentence count/length ratio/terminology hits | pronoun, character appellation, speech tic consistency |
| Academic | terminology hits, numbers/units, abbreviations | discipline terminology consistency across chapters |
| Poetry | line count/section consistency | line structure/imagery |

> Tolerance: reasonable word-order adjustment, natural free translation, stylistic polishing are not problems — narrative translation has high tolerance; review prefers omission over over-flagging.
