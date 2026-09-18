<!-- i18n: source=poetry.zh.md sha256=6ef20b14ab5e8e69b632a0d4b92bb52d8224e4fef454bf1ddb3d89e787105571 -->
> **English** | [中文](poetry.zh.md)

# Poetry and Prose · Translation Optimization Document

> The dedicated optimization specification for poetry and prose. The core of this genre is
> **form carrying meaning** (line breaks, meter, rhyme, imagery, rhythm); translation cannot
> merely seek literal fidelity.

## 1. Genre Positioning and Identification Features

Identification features:

- Poetry: line/section breaks, meter or free verse, rhyme, dense imagery;
- Prose: essays/short sketches, emphasizing mood and rhythm, with loose and free paragraphs;
- Frontmatter/backmatter is **minimal**: usually only title, body, and optional notes.

## 2. Structural Features and Frontmatter/Backmatter Focus

| Region | Handling |
|---|---|
| Title | Needs translation, concise |
| Body (lines/sections) | Preserve line structure and sections |
| Notes (if any) | Preserve bidirectional jumps |
| Dedication/epigraph | Needs translation |

## 3. Analysis Dimensions (consulted by the agent when writing analysis/)

| Field | Meaning |
|---|---|
| `form` | Form (free verse/metered verse/prose poem/essay) |
| `meter` | Meter / syllables |
| `rhyme` | Rhyme |
| `imagery` | Imagery system |

## 4. Terminology and Entity Table

- Usually few proper nouns; occasionally personal names/place names/allusions need annotation.
- If allusions/culturally loaded words are present, record them in the glossary as `type=term` with a `note` explanation.

## 5. Translation Guidance

1. **Preserve line structure and line breaks** (the lifeline of poetry);
2. **Imagery takes priority over the literal**: the literal may be moderately adjusted to preserve imagery;
3. **Explicitly declare the rhyme strategy** (a key trade-off):
   - `keep_meaning`: keep meaning, discard rhyme (recommended default, readability first);
   - `keep_rhyme`: keep rhyme, discard part of the literal (an option for metered verse);
4. Rhythm and feel expressed naturally in the target language, not mechanically word-for-word.

## 6. Review Focus (Mapping to QC)

| QC gate | Poetry focus |
|---|---|
| G0 | Line-count/section consistency (alignment completeness) |
| G1 | Focus on `missing` (loss of imagery), disordered line breaks |
| G2 | Evidence: annotations for allusions/culturally loaded words |
| G3 | Cross-paragraph consistency of imagery/fixed imagery |

**Tolerance**: poetry translation allows great literal freedom; review reports only **loss of imagery, broken line structure, obvious mistranslation**, not wording differences.

## 7. Special Optimization Checklist

- [ ] Line structure/sections preserved (alignment aligned by line)
- [ ] Imagery first + rhyme strategy declared
- [ ] Annotations for allusions/culturally loaded words
- [ ] Review detection of missing (loss of imagery) + disordered line breaks
- [ ] High tolerance (does not report wording differences)
