"""Build the Experiment 4 development corpus (``tasks-exp4-dev.jsonl``).

A fresh 12 small + 12 heavy tasks for tuning tiered-rendering policies, kept
strictly disjoint from the 24 held-out one-shot tasks in ``tasks-oneshot.jsonl``
(and therefore from ``tasks-heavy.jsonl``). Policies are swept on this dev corpus
only; the held-out 24 are never used for tuning.

Heavy tasks are mined the same way as ``build_heavy.py`` (django and sympy at their
pinned SHAs, ``HEAVY_FILTERS``), then the held-out heavy SHAs are removed and 12
are selected stratified by diff size. Small tasks are drawn from the existing
``tasks.jsonl`` pool with the held-out small SHAs removed. Deterministic: the same
pins and the same held-out set yield the same dev corpus.

    python benchmarks/agentic/build_exp4_dev.py --cache ~/.cache/redcon-agentic-heavy
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from agent_arm import select_pilot_tasks  # noqa: E402
from build_heavy import select_heavy  # noqa: E402
from corpus import build_tasks  # noqa: E402
from repos_heavy import HEAVY_FILTERS, REPOS_HEAVY  # noqa: E402
from runner import ensure_clone  # noqa: E402


def _held_out_shas(tasks_dir: Path) -> set[str]:
    """The 24 held-out one-shot SHAs, never used for policy tuning."""
    shas: set[str] = set()
    for line in (tasks_dir / "tasks-oneshot.jsonl").read_text().splitlines():
        if line.strip():
            shas.add(json.loads(line)["sha"])
    return shas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache", type=Path, default=Path.home() / ".cache" / "redcon-agentic-heavy"
    )
    parser.add_argument("--out", type=Path, default=_HERE / "tasks-exp4-dev.jsonl")
    parser.add_argument("--max-per-repo", type=int, default=60)
    args = parser.parse_args()

    held_out = _held_out_shas(_HERE)
    print(f"held-out one-shot SHAs (excluded): {len(held_out)}")

    # Heavy: mine the candidate pool, drop held-out, select a fresh stratified 12.
    heavy_pool: list[dict] = []
    for spec in REPOS_HEAVY:
        repo_path = ensure_clone(spec.name, spec.url, spec.ref, args.cache)
        tasks = build_tasks(
            repo_path, spec.name, rev=spec.ref, max_tasks=args.max_per_repo, **HEAVY_FILTERS
        )
        fresh = [t.to_json() for t in tasks if t.sha not in held_out]
        print(f"{spec.name} @ {spec.ref[:9]}: {len(tasks)} candidates, {len(fresh)} after held-out")
        heavy_pool += fresh
    heavy = select_heavy(heavy_pool)
    assert not (set(t["sha"] for t in heavy) & held_out), "heavy dev leaked a held-out task"

    # Small: drop held-out from the existing pool, select a fresh stratified 12.
    small_all = [
        json.loads(line)
        for line in (_HERE / "tasks.jsonl").read_text().splitlines()
        if line.strip()
    ]
    small_pool = [t for t in small_all if t["sha"] not in held_out]
    small = select_pilot_tasks(small_pool, per_stratum=4)
    assert not (set(t["sha"] for t in small) & held_out), "small dev leaked a held-out task"

    combined = small + heavy
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for task in combined:
            handle.write(json.dumps(task, sort_keys=True) + "\n")
    print(f"wrote {len(combined)} tasks to {args.out}")
    print("small by repo:", dict(Counter(t["repo"] for t in small)))
    print("small strata:", dict(Counter(t.get("stratum") for t in small)))
    print("heavy by repo:", dict(Counter(t["repo"] for t in heavy)))
    print("heavy strata:", dict(Counter(t.get("stratum") for t in heavy)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
