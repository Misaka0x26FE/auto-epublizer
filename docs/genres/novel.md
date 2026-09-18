<!-- i18n: source=novel.zh.md sha256=fccb31a3395ed7bc1baaa62777a93b5bcd93320afad14683f0544584e0d5da43 -->
> **English** | [中文](novel.zh.md)

# Novel Narrative · Translation Optimization Document

> This document is the dedicated optimization specification for the novel genre,
> implementing the `analyzer.py`, `langprofile.py` and `glossary/store.py` mechanisms of
> wenyi (`trans_novel`). Use it together with the chunk translation flow in
> `docs/translation-flow.md` and the review gates in `docs/quality-control.md`.

## 1. Genre Positioning and Identification Features

The novel is a **narrative form**: organized by chapters/divisions, with characters,
dialogue, plot progression and character arcs. It serves narration, not retrieval.

Identification features:

- Has dialogue, psychological description, scene description; chapter titles are mostly narrative;
- Frontmatter/backmatter is **minimal**: cover, title page, copyright page, dedication, preface (optional), table of contents (optional), body, afterword;
- **Generally has no** index, explanatory notes, references or footnotes (except for special "annotated translation/collated edition" versions).

## 2. Structural Features and Frontmatter/Backmatter Focus

| Region | Handling |
|---|---|
| Cover/title page/copyright page | Basically transcribed as-is, only metadata cataloguing |
| Dedication | Short, needs translation, layout preserved |
| Preface (preface by another/author's preface)/foreword | Prose, needs translation, needs understanding (corresponds to `analysis/units/`) |
| Body | The main battlefield of translation, chunked by chapter → paragraph → sentence |
| Afterword/postscript | Prose, needs translation |
| Index/references/footnotes | Usually none; if present (annotated translation) keep bidirectional jumps per academic conventions |

## 3. Analysis Dimensions (agent writes → `analysis/style.md`)

| Field | Meaning | Example |
|---|---|---|
| `genre` | Genre | youth campus / cold third person / suspense |
| `tone` | Overall tone / style | cold and restrained, poetic |
| `narration` | Narrative person and tense | first-person limited, past tense |
| `pacing` | Sentence rhythm | ratio of long to short sentences, paragraph density |
| `register` | Register | written / colloquial / degree of classicalness |
| `dialogue_style` | Dialogue style | verbal tics, modal particles, forms of address |
| `rhetoric` | Rhetorical tendency | density of metaphor, mode of psychological description |

## 4. Character Bible and Terminology

### 4.1 Character Bible

Each character `{source, reading, target, gender, note}`, where `note` must include **manner of speech: self-reference, verbal tics, honorific habits**:

```json
{"source":"五河士道","reading":"いつかわしどう","target":"五河士道","gender":"male",
 "note":"Gentle good-natured person; calls himself 「俺」; calls his sister 「琴里」"}
```

Seeded into the glossary as the unified baseline for translating the whole book. Dialogue must be translated with distinctiveness according to each character's verbal tics/self-reference/honorifics.

### 4.2 Terminology-Type Whitelist

| Type | Description | Matching method |
|---|---|---|
| `人物` person | Personal names | source + alias |
| `地名/组织/术语` | Ordinary entities | source + alias |
| `称谓` appellation | Address variants such as titles/kinship/nicknames | **full source only** |
| `敬称` honorific | 先輩→senior, ちゃん→little X, etc. | **full source only** |
| `口癖` speech | Character catchphrases | **full source only** |
| `固定表达` fixed_expr | Incantations/slogans/fixed lines | **full source only** |

**source-only mechanism** (wenyi `_SOURCE_ONLY_TYPES`): appellations/honorifics/verbal tics/fixed expressions are matched exactly only by the full original text, avoiding bare-name aliases wrongly injecting tone-/scene-derived renderings into ordinary forms of address.

## 5. Translation Guidance

1. Be faithful to the original, never omit, add, merge or split paragraphs; preserve the original paragraphing;
2. Preserve the narrative person and tone; strictly enforce the style guide's person, sentence rhythm and register;
3. Translate dialogue with distinctiveness according to each character's verbal tics/self-reference/honorifics; express psychology and rhetoric naturally per Chinese novel conventions, neither stiffly literal nor piled with translationese;
4. Pronoun reference, forms of address for characters and tone stay coherent across paragraphs (via rolling injection of the previous translation);
5. Honorific strategy (Japanese source), choose one of three: `keep_style` (reflect tone) / `normalize` (unified rules) / `drop` (omit).

## 6. Review Focus (Mapping to QC)

| QC gate | Novel focus |
|---|---|
| G0 | Sentence-count consistency, length ratio, empty translations, terminology hits (source-only exact match) |
| G1 | Focus on `pronoun` (person/gender pronouns), character-address consistency, verbal-tic consistency |
| G2 | Evidence: glossary entries + previous-context character-address context |
| G3 | Conflict arbitration focuses on cross-chapter consistency of character addresses/fixed expressions |

**Tolerance**: reasonable word-order adjustment, natural free translation and stylistic polishing **do not count as problems** — novel translation has high tolerance, and review should err on the side of omission rather than over-flagging.

## 7. Language-Specific Optimization (langprofile)

| Source language | Key points |
|---|---|
| `ja` | Honorific strategy; first person (私/僕/俺/あたし) domains and pronouns; onomatopoeia/mimetic words follow Chinese conventions; Han-character words ≠ Chinese words, do not copy directly; furigana 〘〙 for interpretation only, strictly forbidden to write in |
| `en` | No honorifics, Mr./Ms./Sir consistent throughout; decide "he/she/it" from name gender and context; tense/relative clauses/long sentences restructured per Chinese, passive to active as appropriate; proper-noun transliteration |

## 8. Special Optimization Checklist

- [ ] Character bible extracted and seeded into the glossary
- [ ] source-only terminology types (appellations/honorifics/verbal tics/fixed expressions)
- [ ] Honorific strategy declared (Japanese source)
- [ ] Dialogue distinctiveness (verbal tics/self-reference/honorifics)
- [ ] Rolling injection of previous translation (linking pronouns/addresses/tone)
- [ ] Review pronoun weighting + high tolerance
