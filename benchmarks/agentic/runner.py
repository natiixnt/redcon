"""Run redcon pack over the task corpus and record per-run metrics.

For every task x budget x phrasing, the runner checks out the parent state of
the commit in a git worktree, runs ``redcon pack`` there with default settings
(so no repository's own redcon.toml can skew the comparison), and records:

- file_hits:          recall of the changed files among the packed files.
- region_containment: fraction of changed line ranges that the packed
                      selection actually surfaces (verbatim lines, not summary).
- input_tokens:       estimated input tokens of the pack.
- baseline_tokens:    whole-repo baseline the pack is measured against.
- risk:               redcon's quality-risk estimate.
- cache_key:          the deterministic prompt_cache_key of the packed content.
- elapsed:            wall-clock seconds for the pack.

Results are appended to a JSONL file. Runs are deterministic: the pack output
depends only on the parent state, the phrasing and the budget, never on cache
state or run order.
"""

from __future__ import annotations

import json
import subprocess
import time
import traceback
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from redcon.config import default_config
from redcon.core import pipeline

BUDGETS = (12_000, 30_000, 60_000)
PHRASINGS = ("precise", "medium", "vague")


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return proc.stdout


def ensure_clone(spec_name: str, url: str, ref: str, cache_dir: Path) -> Path:
    """Return a local clone of *url* pinned to *ref*, cloning into cache if needed."""
    dest = cache_dir / spec_name
    if not (dest / ".git").exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--quiet", url, str(dest)], check=True)
    _git(dest, "fetch", "--quiet", "origin", ref)
    return dest


def _covered_lines(entry: dict) -> set[int] | None:
    """Return the packed line coverage of a file, or None for whole-file coverage."""
    if entry.get("strategy") == "full":
        return None  # every line is present
    lines: set[int] = set()
    for rng in entry.get("selected_ranges", []) or []:
        start = int(rng.get("start_line", 0))
        end = int(rng.get("end_line", start))
        lines.update(range(start, end + 1))
    return lines  # empty for a summary that surfaces no verbatim lines


def _region_containment(task: dict, compressed: list[dict]) -> float:
    """Fraction of changed line ranges whose lines the pack actually surfaces."""
    by_path = {entry.get("path"): entry for entry in compressed}
    total = 0
    covered = 0
    for path, hunks in task["hunk_names"].items():
        entry = by_path.get(path)
        coverage = _covered_lines(entry) if entry is not None else set()
        for hunk in hunks:
            total += 1
            start, end = hunk["range"]
            if entry is None:
                continue
            if coverage is None or any(start <= line <= end for line in coverage):
                covered += 1
    return covered / total if total else 0.0


def _file_hits(task: dict, files_included: list[str]) -> float:
    changed = set(task["changed_files"])
    if not changed:
        return 0.0
    return len(changed & set(files_included)) / len(changed)


def run_one(worktree: Path, task: dict, phrasing: str, budget: int) -> dict:
    """Run one pack and return its metric record."""
    started = time.monotonic()
    result = pipeline.run_pack(
        task["phrasings"][phrasing],
        worktree,
        max_tokens=budget,
        config=default_config(),
        record_history=False,
    )
    elapsed = round(time.monotonic() - started, 4)
    data = _as_dict(result)
    budget_block = data.get("budget", {})
    return {
        "repo": task["repo"],
        "sha": task["sha"],
        "phrasing": phrasing,
        "budget": budget,
        "file_hits": round(_file_hits(task, data.get("files_included", [])), 6),
        "region_containment": round(
            _region_containment(task, data.get("compressed_context", [])), 6
        ),
        "input_tokens": int(budget_block.get("estimated_input_tokens", 0)),
        "baseline_tokens": int(data.get("context_baseline_tokens", 0)),
        "risk": str(budget_block.get("quality_risk_estimate", "unknown")),
        "cache_key": str(data.get("prompt_cache_key", "")),
        "elapsed": elapsed,
    }


def _as_dict(result: object) -> dict:
    from redcon.stages.workflow import as_json_dict

    return as_json_dict(result)


@dataclass
class RepoPaths:
    """Where each repo's git clone lives, keyed by corpus repo name."""

    paths: dict[str, Path]


def run_corpus(
    tasks: list[dict],
    repo_paths: dict[str, Path],
    *,
    budgets: tuple[int, ...] = BUDGETS,
    phrasings: tuple[str, ...] = PHRASINGS,
    worktree_root: Path,
) -> Iterator[dict]:
    """Yield a metric record for every task x budget x phrasing.

    Tasks are grouped by parent state so a single worktree serves all nine runs
    for a commit. A checkout or pack failure yields an error record and moves on
    rather than aborting the whole sweep.
    """
    worktree_root.mkdir(parents=True, exist_ok=True)
    for index, task in enumerate(tasks):
        repo_path = repo_paths.get(task["repo"])
        if repo_path is None:
            yield {"repo": task["repo"], "sha": task["sha"], "error": "no clone for repo"}
            continue
        worktree = worktree_root / f"wt-{index}"
        try:
            _git(repo_path, "worktree", "add", "--quiet", "--detach", str(worktree), task["parent_sha"])
        except subprocess.CalledProcessError as exc:
            yield {"repo": task["repo"], "sha": task["sha"], "error": f"checkout failed: {exc}"}
            continue
        try:
            for budget in budgets:
                for phrasing in phrasings:
                    try:
                        yield run_one(worktree, task, phrasing, budget)
                    except Exception as exc:  # noqa: BLE001 - one bad run must not stop the sweep
                        yield {
                            "repo": task["repo"],
                            "sha": task["sha"],
                            "phrasing": phrasing,
                            "budget": budget,
                            "error": f"{type(exc).__name__}: {exc}",
                            "trace": traceback.format_exc(limit=2),
                        }
        finally:
            with _suppress_cleanup():
                _git(repo_path, "worktree", "remove", "--force", str(worktree))


class _suppress_cleanup:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: object) -> bool:
        return True  # worktree cleanup failures must never mask results


def write_results(records: Iterator[dict], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            count += 1
    return count
