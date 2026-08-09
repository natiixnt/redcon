"""Coverage diagnostic: pack file-hits on the heavy corpus across budgets.

Deterministic and free of agent cost. Night 2 measured a pre-injected pack that
covered only ~0.64 of the ground-truth files on django and sympy. This sweep
runs the layer-1 pack over the heavy tasks at several budgets to decide whether
that is a budget limit (coverage climbs toward 1.0 with more tokens) or a ranking
limit (coverage plateaus below ~0.8 regardless of budget).

    python benchmarks/agentic/coverage_sweep.py --cache ~/.cache/redcon-agentic-heavy
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from corpus import read_tasks_jsonl  # noqa: E402
from repos_heavy import REPOS_HEAVY  # noqa: E402
from runner import ensure_clone, run_corpus  # noqa: E402

BUDGETS = (12_000, 30_000, 60_000, 120_000)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache" / "redcon-agentic-heavy")
    parser.add_argument("--tasks", type=Path, default=_HERE / "tasks-heavy.jsonl")
    parser.add_argument("--worktrees", type=Path, default=Path.home() / ".cache" / "redcon-cov-wt")
    parser.add_argument("--out", type=Path, default=_HERE / "results" / "agent-heavy" / "coverage_sweep.json")
    args = parser.parse_args()

    tasks = read_tasks_jsonl(args.tasks)
    repo_paths = {
        spec.name: ensure_clone(spec.name, spec.url, spec.ref, args.cache) for spec in REPOS_HEAVY
    }
    records = [
        r
        for r in run_corpus(
            tasks,
            repo_paths,
            budgets=BUDGETS,
            phrasings=("precise",),
            worktree_root=args.worktrees,
        )
        if "error" not in r
    ]

    by_budget: dict[int, list[float]] = {}
    by_budget_region: dict[int, list[float]] = {}
    for record in records:
        by_budget.setdefault(record["budget"], []).append(record["file_hits"])
        by_budget_region.setdefault(record["budget"], []).append(record["region_containment"])

    summary = []
    for budget in BUDGETS:
        hits = by_budget.get(budget, [])
        summary.append(
            {
                "budget": budget,
                "file_hits": round(st.mean(hits), 4) if hits else 0.0,
                "region_containment": round(st.mean(by_budget_region.get(budget, [0])), 4),
                "n": len(hits),
            }
        )
        print(f"budget={budget:>7}: file_hits={summary[-1]['file_hits']:.3f} (n={len(hits)})")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
