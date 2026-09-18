<!-- i18n: source=analysis.zh.md sha256=9c76ea6d0cc690876b4b6f1c5dade94dce93330653d0f44e30984929ba2c1672 -->
> **English** | [中文](analysis.zh.md)

# Analysis (layered understanding — agent task)

**Single-LLM principle**: understanding is an agent task. The CLI provides only
deterministic helpers (language/genre heuristic detection, `render_style_md` genre-profile
rendering); `analysis/*.md` and the glossary are written by you with your own abilities.

`analysis/` is the context input for translation and review; reading priority is
`analysis/` → `preprocessing/`.

## Output (`analysis/`)

```text
analysis/
├── overview.md            # whole-book content overview (injected as the "book overview" during translation)
├── global.md              # global understanding: theme/point of view/tone/cross-chapter dependencies/high-risk places
├── units/<id>.md          # per-unit understanding: summary/characters appearing/terminology cautions
├── keypoints.md           # key content: difficult paragraphs/complex layout/multilingual fragments
├── style.md               # genre profile (genre + terminology whitelist + translation guidance + language guidance)
├── glossary.csv           # glossary (authoritative, human/agent readable)
├── characters.csv         # character list (novels)
└── glossary_conflicts.jsonl   # terminology-conflict externalization (pending arbitration)
```

## Writing points

1. First read `preprocessing/facts.md` and the understanding artifacts in
   `preprocessing/` (plan/global/units/terms);
2. Write overview/global/units/keypoints (summary, global, per-unit, key points);
3. Language and genre: convert/build use deterministic heuristics (Latin→en, Han→zh,
   Kana→ja, Hangul→ko, Cyrillic→ru…) to annotate `dc:language` for the EPUB (**does not
   write back** to `publication.json.meta`); `meta.genre` detection is not wired — you
   determine the genre yourself and declare it in `style.md`;
4. `style.md`: you may use `render_style_md` to generate a first draft and then adjust it
   to the book (library function, no CLI subcommand;
   `uv run python -c "from auto_translator.analysis import render_style_md; print(render_style_md('novel'))"`),
   or write it directly following `references/style.md`.

## Three states of terminology (agent seeding)

`glossary.csv` column order: `source,target,type,aliases,gender,reading,status,note`.

- Extract person names/place names/organizations/terms from the source and seed them with
  `status=seed` (do not override existing translations); pre-extracting via
  `preprocessing/terms.csv` and importing with `import --terms` also works.
- Reference material imported from `references/user/` may also be seeded.
- Three states: `seed → candidate → conflict → confirmed`; same source with a different
  target is externalized to `glossary_conflicts.jsonl` (done automatically by import)
  pending your final arbitration and write-back.

## Terminology categories

`person` / `place` / `org` / `term` / `event` / `period` / `work` / `fixed_expr`. Novels
additionally include `appellation` / `honorific` / `speech` — these are **source-only**
classification annotations of the genre profile (reminding you to stay consistent during
translation); the terminology hit check uniformly matches all types by
literal/word-boundary matching, with no special branches.

## Notes

- `analysis/` is an intelligent artifact and can be re-run/overwritten; after changing
  terminology/understanding you must overwrite the later stages of the affected units.
- When background knowledge is needed, route it per "fill in background knowledge": if you
  have a search tool, verify and write to `references/web/`; otherwise ask the user and put
  it in `references/user/`.
