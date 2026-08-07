"""Build the context-heavy task corpus (``tasks-heavy.jsonl``).

Mines django and sympy (pinned SHAs, see ``repos_heavy.py``) for commits that
touch several files across at least two directories with a substantial diff, then
selects twelve tasks stratified by diff size (4 small / 4 medium / 4 large, split
evenly between the two repos). Deterministic: the same pins yield the same twelve.

    python benchmarks/agentic/build_heavy.py --cache ~/.cache/redcon-agentic-heavy
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_REPO_ROOT))  # import redcon from the checkout

from corpus import build_tasks  # noqa: E402
from repos_heavy import HEAVY_FILTERS, REPOS_HEAVY  # noqa: E402
from runner import ensure_clone  # noqa: E402

PER_STRATUM = 4  # 12 tasks over 3 size terciles
STRATA = ("small", "medium", "large")


def _size(task: dict) -> int:
    span = 0
    for hunks in task.get("hunk_names", {}).values():
        for hunk in hunks:
            start, end = hunk["range"]
            span += max(1, end - start + 1)
    return span


def select_heavy(tasks: list[dict], *, per_stratum: int = PER_STRATUM) -> list[dict]:
    """4 tasks per size tercile, split evenly across the repos present."""
    ranked = sorted(tasks, key=lambda t: (_size(t), t["sha"]))
    count = len(ranked)
    first, second = count // 3, 2 * count // 3
    bands = {"small": ranked[:first], "medium": ranked[first:second], "large": ranked[second:]}
    repos = sorted({t["repo"] for t in tasks})
    per_repo = max(1, per_stratum // len(repos))
    picked: list[dict] = []
    seen: set[str] = set()
    for name in STRATA:
        by_repo: dict[str, list[dict]] = {}
        for task in bands[name]:
            by_repo.setdefault(task["repo"], []).append(task)
        chosen: list[dict] = []
        for repo in repos:
            group = by_repo.get(repo, [])
            # near-median tasks of this repo within the band
            mid = len(group) // 2
            for offset in range(len(group)):
                for idx in (mid + offset, mid - offset):
                    if 0 <= idx < len(group) and group[idx]["sha"] not in {c["sha"] for c in chosen}:
                        chosen.append(group[idx])
                        break
                if len([c for c in chosen if c["repo"] == repo]) >= per_repo:
                    break
        for task in chosen[:per_stratum]:
            if task["sha"] not in seen:
                seen.add(task["sha"])
                picked.append({**task, "stratum": name})
    return picked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache" / "redcon-agentic-heavy")
    parser.add_argument("--out", type=Path, default=_HERE / "tasks-heavy.jsonl")
    parser.add_argument("--max-per-repo", type=int, default=40)
    args = parser.parse_args()

    pool: list[dict] = []
    for spec in REPOS_HEAVY:
        repo_path = ensure_clone(spec.name, spec.url, spec.ref, args.cache)
        tasks = build_tasks(
            repo_path, spec.name, rev=spec.ref, max_tasks=args.max_per_repo, **HEAVY_FILTERS
        )
        print(f"{spec.name} @ {spec.ref[:9]}: {len(tasks)} candidate tasks")
        pool += [t.to_json() for t in tasks]

    picked = select_heavy(pool)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for task in picked:
            handle.write(json.dumps(task, sort_keys=True) + "\n")
    print(f"wrote {len(picked)} tasks to {args.out}")
    print("stratum:", dict(Counter(t["stratum"] for t in picked)))
    print("repo:", dict(Counter(t["repo"] for t in picked)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
