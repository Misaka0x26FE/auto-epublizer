<!-- i18n: source=publishing.zh.md sha256=596179ea16caa4171b4bf9470cfabed8d96fb3cb1816aff475caf96dbf3197ff -->
> **English** | [中文](publishing.zh.md)

# Publishing and distribution (publishing gate)

> **Positioning**: `qa`'s `released=true` only means **delivery quality** is qualified (accurate/complete/consistent/compliant/
> structurally correct/reproducible) ≠ **publishable**. Publishing is a semantic and legal decision by the agent + user; this document is the
> pre-publishing gate checklist. The repository principle "makes no value/ideological judgements about content" is unchanged — what is managed here
> is the **delivery compliance** of rights, privacy and attribution, not content review.

## 1. Pre-publishing gate (execute in order; stop if any fails)

> Prerequisite: the delivery audit (`references/delivery.md`) is complete — `qa released` + independent reconciliation +
> sampling + `reviews/delivery-<ts>.md` records all in place; this gate governs rights/privacy/attribution on top of that.

### 1.1 Rights basis confirmation

- Confirm the **redistribution permission** of the original book: public domain / authorized translation publication / own copyright self-translation self-publishing.
- Basis sources: the authorization materials in `references/user/`, publisher permission, the original book's copyright page statement
  (`publication.json.meta.rights`).
- **Unclear rights → default to private repository distribution, or stop and ask the user**; do not make legal assumptions on the user's behalf.
- The rights conclusion is recorded in the publishing notes (one sentence + basis), not written into code or configuration.

### 1.2 Privacy scan (publishing tree + git history)

Scan target: all content to be pushed in the publishing repository. Check items:

| Check | Method | Handling |
|---|---|---|
| Credentials/keys | Full-text scan for API key/token patterns (`sk-`, `AKIA`, long random string assignments, `MINERU_API_KEY=` etc.) | Delete the content + revoke the credential (once committed it is considered leaked) |
| Local paths | Scan for `/home/<user>/`, `/Users/`, `C:\Users\`, host names | Replace with portable forms (`~/`, relative paths) |
| User personal data | Real names, emails, addresses in reports/lessons/README/commit messages | Anonymize or obtain consent |
| Original book body copyright material | Source files (`source/`) **are not included in the repo**; templates/examples contain no copyrightable original text | Publish only the translated product and workspace structure |
| Image/cover rights | Consistent with the original book (see §2 cover gate) | Do not use when rights are unclear |

- **`.gitignore` cannot remove already-tracked files** — when sensitive files have been committed, you must `git rm --cached`
  and perform history cleanup (rewriting history is a destructive operation; confirm with the user first).
- Spot-check historical commits with `git log -p` for the above content.

### 1.3 README attribution record

The publishing README must contain (missing = do not publish):

- **Original book bibliographic record**: title, author, edition, ISBN (if any), source language;
- **Rights statement**: one sentence (based on the conclusion in §1.1);
- **Translator attribution**: consistent with `publication.json.meta.translator` (default = agent framework name,
  e.g. OpenCode/DouBao; user-specified name takes priority);
- **No misrepresentation**: do not write metadata the builder/CLI does not actually output, do not falsely list contributors.

### 1.4 Finished-product verification

- **Re-download** the uploaded assets from the publishing channel and check the sha256 matches the local one;
- Open and verify rendering (TOC/illustrations/footnote popups) in at least one reader (e.g. Foliate/Apple Books).

## 2. Cover gate

- The cover is used only after **confirming it may be redistributed** (`facts.json`'s `media.cover_candidates` is candidate
  data, not proof of authorization); unclear rights → deliver without a cover (qa's `W_NO_COVER` is acceptable).
- When the cover file is inconsistent with the original book's layout (self-made cover), the README states "the cover is self-made for the translated edition".

## 3. Publishing operations

- Tag convention: `<slug>-v<N>` (e.g. `the-big-clocks-v1`); the release attaches the finished EPUB +
  sha256.
- **Publish a new version to fix errors**: on discovering a finished-product issue → fix `translation/`+`align/` → rebuild → re-qa →
  publish `-v<N+1>`; **do not force-push, do not overwrite an already-published tag**.
- **Forbidden to `git add -A` in a directory containing source files**: confirm `source/` is not in the publishing tree before staging;
  prefer explicitly listing file names.
- The publishing record (version/date/change summary) is appended to the publishing repository's CHANGELOG or release note,
  not written back to this workspace.

## 4. Guidance relationships

- Full set of release conditions and error-code handling → `references/invariants.md`;
- G5 interpretation and revision convergence → `references/review.md`;
- Finished-product build and determinism → `references/build.md`.
