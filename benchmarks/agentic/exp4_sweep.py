"""Deterministic tiered-rendering policy sweep for Experiment 4 (Phase A).

No agent spend: for each dev-corpus task and each render policy this builds a pack
and measures pack-level quantities only - ground-truth coverage, the fraction of
ground-truth files delivered whole, files included, and budget use - so a policy
can be chosen before any model run. Runs on ``tasks-exp4-dev.jsonl`` only; the
24 held-out one-shot tasks are never touched here.

    python benchmarks/agentic/exp4_sweep.py --cache ~/.cache/redcon-agentic-heavy
"""

from __future__ import annotations

import argparse
import contextlib
import json
import statistics as st
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_HERE))

from redcon.config import CompressionSettings, RedconConfig  # noqa: E402
from redcon.core import pipeline  # noqa: E402
from redcon.stages.workflow import as_json_dict  # noqa: E402

from oneshot_arm import _repo_budget  # noqa: E402
from repos import REPOS  # noqa: E402
from repos_heavy import REPOS_HEAVY  # noqa: E402
from runner import ensure_clone  # noqa: E402

# Baselines plus the three tiered candidate families. "compressed" and plain
# "adaptive" bound the space; the tiered policies trade whole-file budget for
# compressed coverage.
POLICIES = [
    ("compressed", {"render_mode": "compressed", "tiered_policy": ""}),
    ("adaptive", {"render_mode": "adaptive", "tiered_policy": ""}),
    ("split:0.3", {"render_mode": "adaptive", "tiered_policy": "split:0.3"}),
    ("split:0.5", {"render_mode": "adaptive", "tiered_policy": "split:0.5"}),
    ("split:0.7", {"render_mode": "adaptive", "tiered_policy": "split:0.7"}),
    ("topk:5", {"render_mode": "adaptive", "tiered_policy": "topk:5"}),
    ("topk:10", {"render_mode": "adaptive", "tiered_policy": "topk:10"}),
    ("score:2.0", {"render_mode": "adaptive", "tiered_policy": "score:2.0"}),
]


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _corpus(repo: str) -> str:
    return "heavy" if repo in ("django", "sympy") else "small"


def _pack_metrics(worktree: Path, task: dict, budget: int, opts: dict) -> dict:
    cfg = RedconConfig(
        compression=CompressionSettings(
            render_mode=opts["render_mode"], tiered_policy=opts["tiered_policy"]
        )
    )
    data = as_json_dict(
        pipeline.run_pack(
            task["phrasings"]["precise"],
            worktree,
            max_tokens=budget,
            config=cfg,
            render_mode=opts["render_mode"],
            record_history=False,
        )
    )
    gt = set(task["changed_files"])
    entries = data.get("compressed_context") or []
    included = {e["path"] for e in entries if e.get("path")}
    whole_paths = {e["path"] for e in entries if e.get("delivery") == "whole"}
    coverage = len(gt & included) / len(gt) if gt else 0.0
    gt_whole = len(gt & whole_paths) / len(gt) if gt else 0.0
    est = data["budget"]["estimated_input_tokens"]
    return {
        "coverage": coverage,
        "gt_whole": gt_whole,
        "files": len(entries),
        "budget_use": est / budget if budget else 0.0,
        "over_budget": est > budget,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache", type=Path, default=Path.home() / ".cache" / "redcon-agentic-heavy"
    )
    parser.add_argument("--tasks", type=Path, default=_HERE / "tasks-exp4-dev.jsonl")
    parser.add_argument("--worktrees", type=Path, default=Path.home() / ".cache" / "redcon-exp4-wt")
    parser.add_argument("--out", type=Path, default=_HERE / "results" / "exp4-sweep" / "sweep.jsonl")
    args = parser.parse_args()

    tasks = [json.loads(line) for line in args.tasks.read_text().splitlines() if line.strip()]
    specs = {s.name: s for s in (*REPOS, *REPOS_HEAVY)}
    repo_paths = {
        name: (_REPO_ROOT if name == "redcon" else ensure_clone(
            specs[name].name, specs[name].url, specs[name].ref, args.cache))
        for name in sorted({t["repo"] for t in tasks})
        if name in specs
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    counter = 0
    with args.out.open("w", encoding="utf-8") as handle:
        for task in tasks:
            if task["repo"] not in repo_paths:
                continue
            repo = repo_paths[task["repo"]]
            counter += 1
            worktree = args.worktrees / f"wt-{counter}"
            with contextlib.suppress(subprocess.CalledProcessError):
                _git(repo, "worktree", "remove", "--force", str(worktree))
            _git(repo, "worktree", "add", "--quiet", "--detach", str(worktree), task["parent_sha"])
            try:
                budget = _repo_budget(worktree)
                for name, opts in POLICIES:
                    m = _pack_metrics(worktree, task, budget, opts)
                    row = {
                        "sha": task["sha"], "repo": task["repo"], "corpus": _corpus(task["repo"]),
                        "policy": name, "budget": budget, **m,
                    }
                    rows.append(row)
                    handle.write(json.dumps(row, sort_keys=True) + "\n")
                    handle.flush()
            finally:
                with contextlib.suppress(subprocess.CalledProcessError):
                    _git(repo, "worktree", "remove", "--force", str(worktree))
            print(f"[{counter}/{len(tasks)}] {task['repo']}/{task['sha'][:9]} done")

    # Aggregate table: per policy per corpus.
    agg: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        agg[(r["policy"], r["corpus"])].append(r)
    print("\n=== Exp 4 policy sweep (dev corpus, deterministic, no agent spend) ===")
    print("%-11s %-6s %3s %9s %9s %7s %9s %s" % (
        "policy", "corpus", "n", "GT-cov", "GT-whole", "files", "budget", "over"))
    for name, _ in POLICIES:
        for corpus in ("small", "heavy"):
            sub = agg[(name, corpus)]
            if not sub:
                continue
            over = sum(1 for r in sub if r["over_budget"])
            print("%-11s %-6s %3d %9.3f %9.3f %7.1f %9.2f %d" % (
                name, corpus, len(sub),
                st.mean(r["coverage"] for r in sub),
                st.mean(r["gt_whole"] for r in sub),
                st.mean(r["files"] for r in sub),
                st.mean(r["budget_use"] for r in sub),
                over,
            ))
    print(f"\nwrote {len(rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
