"""review 服务：G1 逐批审校 → G2 取证 → G3 仲裁/影子修订/盲复审收敛。

产出 ``reviews/review-<ts>/`` 运行目录；正式 translation/glossary/publication.json 只读，
修订只发生在影子 overlay（shadow_overlay.json）。report.json 由 ``qa`` 命令聚合生成。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from auto_common.llm.base import LLMClient
from auto_common.workspace import RunStore, atomic_write_json

from .._parallel import map_parallel
from ..agents.review_agents import ArbiterAgent, EvidenceAgent, FixerAgent
from ..agents.reviewer import ReviewerAgent
from ..glossary import Glossary, load_glossary_csv
from ..translation.align import read_align
from .convergence import TERMINATION_CLEAN, ConvergenceState, advance, summarize
from .models import VERDICT_CONFIRMED, VERDICT_DISMISSED, Issue, Patch


def _batch(rows: list[dict[str, Any]], size: int = 10) -> list[list[dict[str, Any]]]:
    return [rows[i : i + size] for i in range(0, len(rows), size)]


class ReviewRun:
    """一次审校运行：管理运行目录与收敛循环。"""

    def __init__(self, store: RunStore, client: LLMClient) -> None:
        self.store = store
        self.client = client
        self.ts = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
        self.dir = store.reviews_dir / f"review-{self.ts}"
        self.rounds_dir = self.dir / "rounds"
        self.rounds_dir.mkdir(parents=True, exist_ok=True)
        self.reviewer = ReviewerAgent(client)
        self.evidence = EvidenceAgent(client)
        self.arbiter = ArbiterAgent(client)
        self.fixer = FixerAgent(client)
        self._glossary = Glossary(load_glossary_csv(store.analysis_dir / "glossary.csv"))
        self._book_context = self._load_book_context()
        self._align_cache = self.collect_align_rows()

    def _load_book_context(self) -> str:
        """读取分层理解产物作为 book_context（概览/全局/重点）。

        来源优先级：analysis/ → preprocessing/（agent 预处理产物）。
        """
        parts: list[str] = []
        for name in ("overview.md", "global.md", "keypoints.md"):
            p = self.store.analysis_dir / name
            if p.is_file():
                parts.append(p.read_text(encoding="utf-8"))
        if not parts:
            pre_global = self.store.preprocessing_dir / "global.md"
            if pre_global.is_file():
                parts.append(pre_global.read_text(encoding="utf-8"))
        return "\n\n".join(parts)

    def _evidence_context(self, unit_id: str, seq: int) -> str:
        """为取证组装只读证据：book_context + 术语 + 段落附近上下文。"""
        parts: list[str] = []
        if self._book_context:
            parts.append(self._book_context)
        unit_p = self.store.analysis_dir / "units" / f"{unit_id}.md"
        if unit_p.is_file():
            parts.append(unit_p.read_text(encoding="utf-8"))
        # 段落附近上下文（含目标句的源/译）
        rows = self._align_cache.get(unit_id, [])
        window = [r for r in rows if abs(r.get("seq", 0) - seq) <= 2]
        if window:
            parts.append(
                "段落上下文：\n"
                + "\n".join(f"[{r['seq']}] 源：{r['src']}\n    译：{r['tgt']}" for r in window)
            )
        return "\n\n".join(parts)

    def _write_round(
        self, n: int, issues: list[Issue], patches: list[Patch], summary: dict[str, Any]
    ) -> None:
        d = self.rounds_dir / str(n)
        d.mkdir(parents=True, exist_ok=True)
        atomic_write_json(d / "issues.json", [i.to_dict() for i in issues])
        atomic_write_json(d / "patches.json", [p.to_dict() for p in patches])
        atomic_write_json(d / "summary.json", summary)

    def collect_align_rows(self) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for unit in self.store.load_publication().units:
            rows = read_align(self.store.unit_align_path(unit.id))
            if rows:
                out[unit.id] = rows
        return out

    def _review_batch_task(
        self,
        unit_id: str,
        batch: list[dict[str, Any]],
        shadow: dict[str, dict[int, str]],
        round_no: int,
    ) -> list[Issue]:
        """G1 单个批次审校（并发任务）：返回该批次的 Issue 列表。

        只读 shadow（本轮固定），与其它批次无共享可变状态，可安全并发；
        结果由调用方按稳定原文序合并。
        """
        pairs = []
        for r in batch:
            tgt = shadow.get(unit_id, {}).get(r["seq"], r["tgt"])
            pairs.append({"seq": r["seq"], "src": r["src"], "tgt": tgt})
        issues: list[Issue] = []
        for it in self.reviewer.review_batch(pairs):
            seq = it.get("seq")
            issues.append(
                Issue(
                    issue_id=f"r{round_no}-{unit_id}-{it.get('seq', 0)}",
                    chapter=unit_id,
                    index=it.get("seq", 0),
                    seq=[seq] if isinstance(seq, int) else list(seq or []),
                    type=it.get("type", "mistranslation"),
                    detail=it.get("detail", ""),
                    suggestion=it.get("suggestion", ""),
                )
            )
        return issues

    def _fix_task(
        self, issue: Issue, shadow: dict[str, dict[int, str]]
    ) -> tuple[Issue, str, str] | None:
        """G3 单个 issue 影子修订（并发任务）：解析 before → fixer 计算 after。

        只读 shadow（当前已确认 issue 列表固定），fixer 调用无共享可变状态；
        shadow 的写回由调用方串行应用，避免并发改 dict。
        返回 (issue, before, after)；无 before 返回 None。
        """
        unit_id = issue.chapter
        seq = issue.seq[0] if issue.seq else issue.index
        before = shadow.get(unit_id, {}).get(seq)
        if before is None:
            for r in self._align_cache.get(unit_id, []):
                if r["seq"] == seq:
                    before = r["tgt"]
                    break
        if before is None:
            return None
        after = self.fixer.fix(before, issue.to_dict())
        return issue, before, after

    def run(self, *, clean_confirmations: int = 2, fix_max_rounds: int = 2) -> dict[str, Any]:
        state = ConvergenceState()
        shadow: dict[str, dict[int, str]] = {}  # unit_id -> seq -> tgt
        total_candidates = 0
        total_confirmed = 0
        total_patched = 0
        failed_fixes = 0  # fixer 未产生有效改动（after == before）的积压

        while True:
            round_no = state.rounds + 1
            round_issues: list[Issue] = []
            round_patches: list[Patch] = []

            # G1 逐批审校（批次级并发 + 稳定原文序合并，C7）
            tasks: list[tuple[str, list[dict[str, Any]]]] = [
                (unit_id, batch)
                for unit_id, rows in self._align_cache.items()
                for batch in _batch(rows)
            ]
            per_batch = map_parallel(
                lambda t, rno=round_no: self._review_batch_task(t[0], t[1], shadow, rno),
                tasks,
            )
            for batch_issues in per_batch:
                round_issues.extend(batch_issues)

            total_candidates += len(round_issues)

            # G2 取证裁决（并发只读评估，稳定序合并；C7）
            def _adjudicate(issue: Issue) -> tuple[Issue, str]:
                seq = issue.seq[0] if issue.seq else issue.index
                context = self._evidence_context(issue.chapter, seq)
                verdict = self.evidence.adjudicate(issue.to_dict(), context=context)
                return issue, verdict.get("verdict", "")

            for issue, verdict in map_parallel(_adjudicate, round_issues):
                if verdict == VERDICT_CONFIRMED:
                    issue.verdict = VERDICT_CONFIRMED
                    total_confirmed += 1
                else:
                    issue.verdict = VERDICT_DISMISSED

            # G3 影子修订（并发计算 after，串行应用 shadow；C7）
            confirmed = [i for i in round_issues if i.verdict == VERDICT_CONFIRMED]
            fixed = map_parallel(lambda i: self._fix_task(i, shadow), confirmed)
            for outcome in fixed:
                if outcome is None:
                    continue
                issue, before, after = outcome
                unit_id = issue.chapter
                seq = issue.seq[0] if issue.seq else issue.index
                if after == before:
                    failed_fixes += 1
                else:
                    total_patched += 1
                shadow.setdefault(unit_id, {})[seq] = after
                round_patches.append(
                    Patch(
                        patch_id=f"p{round_no}-{unit_id}-{seq}",
                        chapter=unit_id,
                        index=seq,
                        before_hash=summarize([{"seq": seq, "tgt": before}])[:16],
                        after=after,
                        issue_ids=[issue.issue_id],
                        review_round=round_no,
                    )
                )

            # 汇总影子
            shadow_rows = []
            for unit_id, rows in self._align_cache.items():
                for r in rows:
                    shadow_rows.append(
                        {"seq": r["seq"], "tgt": shadow.get(unit_id, {}).get(r["seq"], r["tgt"])}
                    )
            shadow_summary = summarize(shadow_rows) if shadow_rows else None

            unresolved = failed_fixes > 0 and not confirmed
            result = advance(
                state,
                has_issues=bool(confirmed),
                shadow_summary=shadow_summary,
                unresolved=unresolved,
                clean_confirmations=clean_confirmations,
                fix_max_rounds=fix_max_rounds,
            )

            self._write_round(
                round_no,
                round_issues,
                round_patches,
                {
                    "issues": len(round_issues),
                    "confirmed": len(confirmed),
                    "termination": result.termination,
                },
            )

            if result.done:
                break

        # 终局落盘
        if shadow:
            atomic_write_json(self.dir / "shadow_overlay.json", shadow)
        result_json = {
            "issue_count": total_confirmed,
            "g1_candidates": total_candidates,
            "g2_confirmed": total_confirmed,
            "g3_patched": total_patched,
            "termination": result.termination,
            "rounds": result.rounds,
        }
        atomic_write_json(self.dir / "result.json", result_json)
        atomic_write_json(
            self.dir / "metadata.json",
            {"ts": self.ts, "clean_confirmations": clean_confirmations},
        )
        # 本轮用量增量只合并一次（run_id 幂等，重试/续跑不重复计费）
        self.store.merge_usage(self.client.usage_summary(), run_id=f"review-{self.ts}")
        # 只有通过审校（clean_confirmed）才标 reviewed；未收敛保留 aligned 供人工处置
        if result.termination == TERMINATION_CLEAN:
            for unit in self.store.load_publication().units:
                if read_align(self.store.unit_align_path(unit.id)):
                    self.store.set_unit_status(unit.id, "reviewed")
        else:
            self.store.log_event(
                "review_unresolved",
                termination=result.termination,
                rounds=result.rounds,
                confirmed=total_confirmed,
            )
        return result_json


def review(
    store: RunStore,
    client: LLMClient,
    *,
    clean_confirmations: int = 2,
    fix_max_rounds: int = 2,
) -> dict[str, Any]:
    run = ReviewRun(store, client)
    return run.run(clean_confirmations=clean_confirmations, fix_max_rounds=fix_max_rounds)
