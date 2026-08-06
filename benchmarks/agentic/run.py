"""Run the full evaluation over the pinned corpus.

Reads ``tasks.jsonl``, packs every task x budget x phrasing at the parent state,
and writes ``results.jsonl`` plus a Markdown ``REPORT.md``.

    python benchmarks/agentic/run.py --cache /tmp/agentic-cache --out-dir results

This is layer 1 (redcon-only, no LLM in the loop): deterministic and free of any
API cost.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_REPO_ROOT))  # import redcon from the checkout

import metrics  # noqa: E402
import report  # noqa: E402
from corpus import read_tasks_jsonl  # noqa: E402
from repos import REPOS  # noqa: E402
from runner import ensure_clone, run_corpus, write_results  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=_HERE / "tasks.jsonl")
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache" / "redcon-agentic")
    parser.add_argument("--out-dir", type=Path, default=_HERE / "results")
    parser.add_argument("--worktrees", type=Path, default=Path.home() / ".cache" / "redcon-agentic-wt")
    args = parser.parse_args()

    repo_paths: dict[str, Path] = {}
    for spec in REPOS:
        if spec.name == "redcon":
            repo_paths[spec.name] = _REPO_ROOT
        else:
            repo_paths[spec.name] = ensure_clone(spec.name, spec.url, spec.ref, args.cache)

    tasks = read_tasks_jsonl(args.tasks)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    results_path = args.out_dir / "results.jsonl"

    records = run_corpus(tasks, repo_paths, worktree_root=args.worktrees)
    total = write_results(records, results_path)
    print(f"wrote {total} records to {results_path}")

    valid, errors = metrics.load_results(results_path)
    summary = metrics.summarize(valid)
    (args.out_dir / "REPORT.md").write_text(report.render(summary, errors=len(errors)), encoding="utf-8")
    print(f"valid runs: {len(valid)}, errors: {len(errors)}")
    print(f"overall file_hits: {summary['overall']['file_hits']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
