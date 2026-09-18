<!-- i18n: source=agent-vs-code.zh.md sha256=225be26db071d65fe1d37517f095133d2c97901ebd0df54847fcc6a704831ef9 -->
> **English** | [中文](agent-vs-code.zh.md)

# Division of Labour Between the Agent and Python Code

This document answers a fundamental architectural question: **which work belongs to Python
code, and which work belongs to the agent.**
It expands the "division of labour" entry in `AGENTS.md` and is the shared criterion for
maintaining and using this project.

## One Main Criterion

> **"The same input must produce the same output" → Python; "requires understanding content, making trade-offs, reaching judgements" → the agent.**

Three auxiliary criteria:

1. **State consistency belongs to Python** — atomic writes, locks, the state machine, idempotence; an agent maintaining state by hand is bound to make mistakes.
2. **The external world belongs to Python** — running pandoc / epubcheck / OCR is a deterministic tool invocation and should not be hand-rolled by the agent;
   while **any "understanding" belongs to the agent** (single-LLM principle: the only LLM in this project is the agent operating the CLI).
3. **Acceptance interpretation belongs to the agent** — a machine can only produce signals; the judgement (how to fix, whether to release) is the agent's job.

In one sentence: **Python is responsible for "not wrong", the agent for "right".**
Determinism, consistency and reproducibility go to code; understanding, trade-offs and final review go to the agent.
The CLI is the agent's hand, not the agent's brain.

## Belongs to Python (tool: it won't lie to you)

| Category | Details |
|---|---|
| Deterministic transformation | ingest (pandoc / PDF page slicing / OCR / illustration / table / formula detection), structure (four-layer classification / cleaning / stable ID), align (sentence alignment), build (EPUB packaging), preprocess facts (sniffing / metadata / TOC / health check / size), PDF content extraction (bookmark chaptering / multi-column reading order / inserts description files) |
| State and consistency | publication.json atomic write / multi-level locks / source_sha256 binding / state machine advancement |
| External tool invocation | pandoc / epubcheck / OCR / MinerU API (external parsing) |
| Deterministic validation | G0 static checks, G4 unpack audit, epubcheck, inserts provenance audit — **signals only, no verdicts** |

## Belongs to the Agent (judge: understands content)

| Category | Details |
|---|---|
| Approach decisions | `preprocessing/plan.md` (ingest route selection + rationale) — the CLI gives facts and hints; the decision is always the agent's |
| Semantic understanding | global / units / terms / risks / overview / keypoints in `preprocessing/` and `analysis/`; distillation of "central idea / style / risks" |
| Translation | `translation/` + `align/` (the CLI only handles structural validation at import time) |
| Review | G1–G3 semantic review (read align to find omissions/mistranslations/terminology violations), revision, convergence determination → `reviews/review-<ts>/result.json` |
| Interpretation and handling | how to fix g0 warnings, how to judge `report.json`, what to do about non-convergence (max_rounds / oscillation / unresolved_fixes), whether to release |
| Final terminology arbitration | `glossary_conflicts.jsonl` → arbitration written back to `glossary.csv` |
| Insert content semantics | `content_desc` (content description) and `latex` (hand-written LaTeX for formulas) of `raw/inserts/<id>.json` |
| **Semantic repair** | fixes for parse defects / OCR noise / structural judgement (line-break re-splitting, misrecognition correction, running head/footer attribution, unit re-splitting) — signals come from facts; repair and traceability belong to the agent, see [semantic-repair.md](semantic-repair.md) |
| Source errata | correction by precedent (e.g. the IDG→IDF class) |
| Agent meta-capability self-report | multimodal (can it see images), search (does it have a search tool) — the CLI cannot detect these in principle; only the agent can say |

## Two Grey Areas

**① Whose are the understanding artifacts in `analysis/`?**
The agent's. `analysis/*.md` and the glossary are written by the agent with its own
abilities (reading `preprocessing/` facts and the `references/style.md` genre profile);
the CLI only provides deterministic helpers (language/genre heuristics, `render_style_md`).

**② Whose are the issues from G1 review?**
The agent's. The issue content is the agent's semantic judgement, but the "better to omit
than to over-flag" constraint, the G0 static signals, and the rules and contracts of the
evidence-gathering process (G2 evidence before verdict) belong to code. The machine gives
signals, the rules govern the process, the agent does the final review.

## One Architectural Corollary

From this boundary follows naturally how this project is decoupled: **the agent's artifacts
are always "files", and Python's job is to "validate files + advance state + consume
files"**. The two sides couple only through file contracts (schema). This explains:

- the agent needs only three abilities — "read files, run shell, write files" — and no MCP / sub-agents / special tools;
- the CLI makes no LLM calls; all semantic work is done by the agent's hand-written artifacts, registered via `import` / review artifacts;
- the agent does not hand-edit `publication.json` — state advances only through CLI commands (`import` / `build` / `qa`…).
