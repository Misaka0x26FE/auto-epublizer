<!-- i18n: source=quality-evidence.zh.md sha256=8948a0a51b0a841c40968872089cccdf7ec1874aac82c133f3b79c837c041cf1 -->
> **English** | [中文](quality-evidence.zh.md)

# Evidence and safe-repair contract

## Read-only command

`auto-epublizer evidence report --workspace <dir> --json [--epub <path>]
[--external-source <file>] [--copy <expected.epub> ...]` recomputes current evidence without
running QA or writing reports/state/events. JSON includes rule version, input digest,
per-check scope, `pass/fail/unknown/manual` and actual evidence. Any fail exits 1;
unknown/manual checks never masquerade as pass.

It hashes the source, reconciles source alignment, md/align and independently normalized
complete product bodies per unit, and separately checks registered notes according to
the actual render mode. Navigation/media reuse existing mechanical gates; source-TOC
semantics still need source review. Unprovided external sources/copy lists remain unknown;
an explicitly expected missing copy fails. There is no released field: this does not
replace QA, source-note inventory or semantic acceptance. Output goes to stdout; choose
a new file yourself if retaining it.

`auto-epublizer evidence source --workspace <dir> --json` exports raw page blocks,
actually available page/bbox/font_size/column values, the source TOC from facts, unit
roles and independent source-note candidates without writing anything. Missing precision
is null. All repeated raw_matches are retained as ambiguous, never reduced to the first
location; code literals are not note candidates. Boundaries include both page numbers
and all unit/block locations; missing or nonconsecutive pages never claim continuation.
Missing raw/facts information is not guessed from filenames or font thresholds; source
note completeness still requires independent page-by-page review.

The report's product_residue scans every package XHTML/HTML document, including semantic
asides and non-spine backmatter, excluding code/pre literals. The ¬/$$ patterns only
produce manual candidates, never automatic edits or definitive defect judgements.

## 1. Identify what was actually proved

- `qa released` establishes known machine contracts, not complete translation, correct
  names, correct index columns or a complete source-note inventory.
- Registered-note/aside equality covers only the registered set. Independently inventory
  printed labels, page boundaries, note typography and placement. Gaps are candidates,
  never permission to invent notes. Pair split heads/tails by source-page evidence.
- Token bags do not establish order, frequency or ownership. Repetition and extractor
  differences are not automatically explained. Garbled extracted text does not prove
  a page image is blank/unreadable: render and actually inspect it before claiming visual review.
- Raw `src==tgt` counts include headings, images, locators and bibliography. State scope,
  normalization, semantic-aside exclusions, denominator and snapshot digest. Separate body,
  index, bibliography and notes; never bulk-move content based on counts alone.

## 2. Structure and indexes

Restore page→column→line order, entries and page continuations before freezing structure
and verifying names. Reconcile source TOC, units, top-level nav, subheadings and landmarks
separately. Header echoes are candidates, not deletion instructions; removing table tags
does not restore a falsely detected bibliography table.

An index is not a bibliography. Do not blanket-exempt an index when the user requires
localized headwords with original spellings in parentheses. Regex-harvested name pairs are
**candidates**: surrounding verbs, job titles, places and near-matching entities may leak in.
Verify source identity, body naming and cross-reference targets individually; preserve original
spelling for lookup. A filled mapping or the presence of Chinese is not semantic acceptance.
Transliteration, aliases and source errata remain agent decisions, never automatic judgements.

## 3. Minimum repair-tool contract

1. Each plan item identifies unit/source location, exact old/new text, evidence file/pages,
   approval state, original file SHA-256 and tool/rule version. Candidates are not approvals.
2. Preserve existing manual mappings. Reject unknown columns, duplicate keys, missing
   translations, ambiguity, unapproved edits and changed baselines; never choose the first
   candidate silently. Use UTF-8 without BOM; terminology retains its separate eight-column schema.
3. **Validate everything before writing**: construct all md/align (and `.tr` when applicable)
   changes in memory; verify fidelity, drift, markers, page numbers, links and original spelling.
   Start the commit phase only after the entire set passes.
4. Dry-run writes neither artifacts, state nor ledger. Actual application needs an explicit
   transaction/backup recovery mechanism: individual `os.replace` calls do not make a group
   atomic. Support interruption recovery; failure must not leave half an updated group.
5. Reruns are idempotent. Reject double wrapping, global alias substitution and regex-prefix
   collisions. Test Unicode initials, quote variants, broken words and numeric continuations
   using failing synthetic fixtures before fixing; do not relax criteria to manufacture green.
6. Never hand-edit publication.json. Register changes through CLI, rebuild and rerun QA;
   do not patch EPUB binaries directly.

## 4. Audit generators and adjudicators

For each check record `pass/fail/unknown/manual`, actual command/input digest, scope,
rule version and evidence. Unexecuted checks are not ticked and conclusions are not fixed
“no defects” text. Mark each check redo/reuse; reuse requires current input/rule binding.
Old explained verdicts must not mask new findings; changed rules require review or invalidation.

- Hash actual source bytes against registration. Missing external sources is unknown;
  multiple candidates are ambiguous. Neither is a three-way match.
- Reconcile actual source/translation/align/product content and positions. Heading hits,
  equal block counts and tautologies cannot substitute for body checks.
- Compare parsed navigation labels/targets/hierarchy in one package-path identity domain,
  not keys with `OEBPS/` on just one side.
- After removing actual backlink/label markup, note content must be nonempty and complete
  under the same normalization. Empty strings or mutual substring inclusion are not completeness.
- Census body, semantic notes and front/backmatter. Legitimate original-language citations
  are not automatically untranslated prose.
- Verify every expected copy, hash and audit binding; missing directories/files fail.
  Skipping an existing MANIFEST is not verification. Check report freshness before packaging;
  keep old copies immutable and create a new versioned directory.

## 5. Operations and public feedback

Use an isolated worktree for CLI repairs; preserve user workspaces. Do not run broad
checkout/reset/clean. Stage only task-owned files; concurrent changes are not grounds for
deletion to make a cleanliness check pass. Upload no manuscripts, source images or secrets.

When reusing another worktree's environment set `PYTHONPATH=src` and verify import paths:
editable installs may otherwise test the wrong checkout. i18n finalize updates stamps,
**not translations**; actually synchronize both languages before running the full suite.

Disclose unperformed source/index semantic review, untested GUI behaviour and heuristic
limits. Issues/PRs state fixed scope and remaining risks; documentation promises and unit
tests are not acceptance evidence for a book.
