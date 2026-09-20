<!-- i18n: source=publishing.zh.md sha256=4175969c1b81f24e200666514fc8db2660df918cc36026cfa7b04f2d8d61bb7b -->
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
- **This project does not review the copyright risk of the processed object**: rights to
  the source files etc. are the user's responsibility; the workspace (including `source/`)
  is **fully tracked in git** and by default is a **private repository** (host configurable,
  default GitHub); making it public requires an explicit user declaration or the user
  handling it themselves.
- **Unclear rights → default to private repository distribution, or stop and ask the user**; do not make legal assumptions on the user's behalf.
- The rights conclusion is recorded in the publishing notes (one sentence + basis), not written into code or configuration.

### 1.2 Privacy scan (publishing tree + git history)

Scan target: all content to be pushed in the publishing repository. Check items:

| Check | Method | Handling |
|---|---|---|
| Credentials/keys | Full-text scan for API key/token patterns (`sk-`, `AKIA`, long random string assignments, `MINERU_API_KEY=` etc.) | Delete the content + revoke the credential (once committed it is considered leaked) |
| Local paths | Scan for `/home/<user>/`, `/Users/`, `C:\Users\`, host names | Replace with portable forms (`~/`, relative paths) |
| User personal data | Real names, emails, addresses in reports/lessons/README/commit messages | Anonymize or obtain consent |
| Original book body copyright material | Source files (`source/`) are **fully tracked** with the workspace (private repo by default; copyright risk is the user's responsibility, not reviewed by this project) | Complete this privacy scan, and obtain an explicit user declaration, before making the repo public |
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
- **The workspace is fully tracked (including `source/`) and is private by default**: the
  repository defaults to **private** (host configurable, default GitHub); before making it
  public, complete the §1.2 privacy scan and obtain an explicit user declaration.
- The publishing record (version/date/change summary) is appended to the publishing repository's CHANGELOG or release note,
  not written back to this workspace.

## 4. Guidance relationships

- Full set of release conditions and error-code handling → `references/invariants.md`;
- G5 interpretation and revision convergence → `references/review.md`;
- Finished-product build and determinism → `references/build.md`.
