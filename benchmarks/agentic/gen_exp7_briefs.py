"""Generate task-independent repository briefs for the night-2 heavy corpus.

For every heavy task, check the source repository out at the task's base commit
and render the brief through the shipped `redcon brief` code path (build_brief),
writing one Markdown brief per (repo, sha). The brief is task-independent, so the
same repo at the same commit always yields the same file; this script builds each
one twice and asserts the two renderings are byte-identical, recording the token
count. Deterministic and free: no agent spend.

    python benchmarks/agentic/gen_exp7_briefs.py \\
        --src-root /path/to/clones --out benchmarks/agentic/results/exp7-phaseA

`--src-root` holds full clones named `django/` and `sympy/`; those clones are not
committed. The generated briefs under `--out` are.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from redcon.brief import build_brief  # noqa: E402

_SHA_LEN = 12


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _checkout(src: Path, sha: str) -> None:
    # Drop any scan index from a prior SHA so the checkout is clean, then hard
    # checkout the base commit.
    redcon_dir = src / ".redcon"
    if redcon_dir.exists():
        subprocess.run(["rm", "-rf", str(redcon_dir)], check=True)
    _git(src, "checkout", "-q", "-f", sha)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src-root", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, default=_HERE / "tasks-heavy.jsonl")
    parser.add_argument("--out", type=Path, default=_HERE / "results" / "exp7-phaseA")
    args = parser.parse_args()

    tasks = [json.loads(line) for line in args.tasks.read_text().splitlines() if line.strip()]
    args.out.mkdir(parents=True, exist_ok=True)

    index = []
    for task in tasks:
        repo = task["repo"]
        sha = task["sha"]
        src = args.src_root / repo
        if not src.exists():
            print(f"skip {repo} {sha[:_SHA_LEN]}: {src} missing", file=sys.stderr)
            continue
        _checkout(src, sha)
        first = build_brief(src)
        second = build_brief(src)
        assert first.text == second.text, f"non-deterministic brief for {repo} {sha}"
        name = f"{repo}-{sha[:_SHA_LEN]}.brief.md"
        (args.out / name).write_text(first.text, encoding="utf-8")
        index.append(
            {
                "repo": repo,
                "sha": sha[:_SHA_LEN],
                "brief": name,
                "tokens": first.tokens,
                "file_count": first.file_count,
                "truncated": first.truncated,
            }
        )
        print(f"{name}: {first.tokens} tokens, {first.file_count} files")

    (args.out / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    if index:
        toks = [row["tokens"] for row in index]
        print(f"\n{len(index)} briefs; tokens min {min(toks)} max {max(toks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
