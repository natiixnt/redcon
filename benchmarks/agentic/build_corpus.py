"""Regenerate ``tasks.jsonl`` from the pinned repositories.

redcon is mined from the local checkout at its release tag; the external repos
are cloned into a cache and mined at their pinned SHA. Deterministic: the same
pins always yield the same corpus.

    python benchmarks/agentic/build_corpus.py --cache /tmp/agentic-cache
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent  # the redcon checkout containing this harness
sys.path.insert(0, str(_REPO_ROOT))  # import redcon from the checkout

from corpus import build_tasks, write_tasks_jsonl  # noqa: E402
from repos import REPOS  # noqa: E402
from runner import ensure_clone  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache" / "redcon-agentic")
    parser.add_argument("--out", type=Path, default=_HERE / "tasks.jsonl")
    parser.add_argument("--max-per-repo", type=int, default=70)
    args = parser.parse_args()

    all_tasks = []
    for spec in REPOS:
        if spec.name == "redcon":
            repo_path, rev = _REPO_ROOT, spec.ref
        else:
            repo_path = ensure_clone(spec.name, spec.url, spec.ref, args.cache)
            rev = spec.ref
        tasks = build_tasks(repo_path, spec.name, rev=rev, max_tasks=args.max_per_repo)
        print(f"{spec.name} @ {spec.ref}: {len(tasks)} tasks")
        all_tasks += tasks

    write_tasks_jsonl(all_tasks, args.out)
    print(f"wrote {len(all_tasks)} tasks to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
