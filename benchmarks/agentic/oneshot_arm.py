"""Experiment 1: one-shot selection quality.

One model call per task, no tool loop. The prompt carries a context - either the
redcon pack or a pinned naive keyword retrieval, both to the same token budget -
and the model must answer with a unified diff. Removing the loop isolates the
quality of the selection from the agent's in-loop behaviour. Cost is equal across
arms by construction; only what was selected differs.

Design and pre-registration: docs/research/exp1-one-shot.md. Not deterministic
(the model is stochastic) and draws on subscription usage, so it is run
deliberately, never in CI. Dollar figures are the CLI's list-price accounting.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent

ARMS = ("redcon", "naive")
MODEL = "sonnet"
CANONICAL_MODEL = "claude-sonnet-5"
DEFAULT_TIMEOUT = 600
# No file tools: the model must answer from the injected context alone.
_NO_TOOLS = ("Bash", "Read", "Edit", "Write", "Grep", "Glob", "Task", "WebFetch", "WebSearch")

_STOPWORDS = {
    "the", "and", "for", "with", "add", "fix", "use", "from", "into", "that", "this",
    "when", "then", "than", "not", "are", "was", "has", "have", "its", "his", "her",
}
_SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx"}


def _claude_bin() -> str:
    import os

    return os.environ.get("CLAUDE_CODE_EXECPATH") or "claude"


def _keywords(subject: str) -> list[str]:
    tokens = re.split(r"[^A-Za-z0-9]+", subject.lower())
    return [t for t in tokens if len(t) >= 3 and t not in _STOPWORDS]


def _iter_source_files(worktree: Path) -> Iterator[Path]:
    out = subprocess.run(
        ["git", "-C", str(worktree), "ls-files"], capture_output=True, text=True, check=True
    ).stdout
    for rel in out.splitlines():
        if Path(rel).suffix.lower() in _SOURCE_EXTS:
            yield worktree / rel


def naive_context(worktree: Path, task: dict, budget: int) -> tuple[str, list[str]]:
    """Pinned baseline retrieval: keyword match-count ranking, whole files to budget.

    Keywords come from the precise phrasing; each file is scored by total keyword
    occurrences; ties break by shorter then lexicographic path; files are included
    whole in rank order until the next file would exceed the budget (bytes/4).
    """
    keywords = _keywords(task["phrasings"]["precise"])
    scored: list[tuple[int, str, str]] = []
    for path in _iter_source_files(worktree):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        low = text.lower()
        score = sum(low.count(kw) for kw in keywords)
        if score:
            scored.append((score, str(path.relative_to(worktree)), text))
    # Higher score first; deterministic tie-break by shorter then lexicographic path.
    scored.sort(key=lambda t: (-t[0], len(t[1]), t[1]))

    budget_chars = budget * 4
    used = 0
    parts: list[str] = ["Potentially relevant files (keyword-ranked):"]
    files: list[str] = []
    for _score, rel, text in scored:
        if used + len(text) > budget_chars:
            continue  # drop whole files that do not fit; keep scanning smaller ones
        parts.append(f"\n### {rel}\n```\n{text}\n```")
        files.append(rel)
        used += len(text)
    return "\n".join(parts), files


def redcon_context(worktree: Path, task: dict, budget: int) -> tuple[str, list[str]]:
    """The redcon pack for the task, rendered, plus the files it included."""
    from redcon.config import default_config  # noqa: PLC0415
    from redcon.core import pipeline  # noqa: PLC0415
    from redcon.core.render import render_pack_markdown  # noqa: PLC0415
    from redcon.stages.workflow import as_json_dict  # noqa: PLC0415

    data = as_json_dict(
        pipeline.run_pack(
            task["phrasings"]["precise"],
            worktree,
            max_tokens=budget,
            config=default_config(),
            record_history=False,
        )
    )
    files = list(data.get("files_included") or [])
    return render_pack_markdown(data), files


def _repo_budget(worktree: Path) -> int:
    """The 1.16 size-scaled default budget for this repo, shared by both arms."""
    from redcon.config import load_config  # noqa: PLC0415
    from redcon.core.budget import (  # noqa: PLC0415
        default_budget_for_repo_tokens,
        estimate_repo_tokens,
    )

    return default_budget_for_repo_tokens(estimate_repo_tokens(worktree, load_config(worktree)))


_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+")
_DIFF_FILE = re.compile(r"^\+\+\+ b/(.+)$")


def parse_unified_diff(text: str) -> dict[str, set[int]]:
    """Parse a unified diff into {file: set of parent-side line numbers it changes}.

    Empty if the text is not a parseable unified diff (the caller scores that as 0).
    """
    files: dict[str, set[int]] = {}
    current: str | None = None
    for line in text.splitlines():
        m = _DIFF_FILE.match(line)
        if m:
            current = m.group(1).strip()
            files.setdefault(current, set())
            continue
        h = _HUNK.match(line)
        if h and current is not None:
            start = int(h.group(1))
            count = int(h.group(2)) if h.group(2) is not None else 1
            files[current].update(range(start, start + max(count, 1)))
    return {f: lines for f, lines in files.items() if lines}


def _gt_lines(task: dict) -> dict[str, set[int]]:
    gt: dict[str, set[int]] = {}
    for path, hunks in task.get("hunk_names", {}).items():
        lines: set[int] = set()
        for hunk in hunks:
            start, end = hunk["range"]
            lines.update(range(start, end + 1))
        gt[path] = lines
    return gt


def diff_overlap(patch_text: str, task: dict) -> dict:
    """File- and line-level overlap of the model's patch with the real commit."""
    patch = parse_unified_diff(patch_text)
    parsed = bool(patch)
    gt_files = set(task["changed_files"])
    patch_files = set(patch)
    file_overlap = len(gt_files & patch_files) / len(gt_files) if gt_files else 0.0

    gt = _gt_lines(task)
    gt_total = sum(len(v) for v in gt.values())
    hit = 0
    for path, gt_lines in gt.items():
        hit += len(gt_lines & patch.get(path, set()))
    line_overlap = hit / gt_total if gt_total else 0.0
    return {
        "parsed": parsed,
        "file_overlap": round(file_overlap, 6),
        "line_overlap": round(line_overlap, 6),
        "patch_files": sorted(patch_files),
    }


def _prompt(context: str, task: dict) -> str:
    return (
        f"{context}\n\n---\n\n"
        "Using only the context above, implement this change:\n\n"
        f"    {task['phrasings']['precise']}\n\n"
        "Respond with ONLY a unified diff (a git-style patch) and nothing else. "
        "Use `--- a/<path>` and `+++ b/<path>` headers and `@@` hunks."
    )


def _command(prompt: str) -> list[str]:
    return [
        _claude_bin(),
        "-p",
        prompt,
        "--model",
        MODEL,
        "--max-turns",
        "1",
        "--output-format",
        "json",
        "--permission-mode",
        "bypassPermissions",
        "--disallowedTools",
        *_NO_TOOLS,
    ]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def run_one(task: dict, arm: str, repeat: int, *, repo_path: Path, worktree: Path,
            transcript_dir: Path | None, timeout: int) -> dict:
    base = {"repo": task["repo"], "sha": task["sha"], "arm": arm, "repeat": repeat,
            "stratum": task.get("stratum")}
    # Clear any stale registration at this path before adding (recurring collision).
    with contextlib.suppress(subprocess.CalledProcessError):
        _git(repo_path, "worktree", "remove", "--force", str(worktree))
    _git(repo_path, "worktree", "add", "--quiet", "--detach", str(worktree), task["parent_sha"])
    try:
        budget = _repo_budget(worktree)
        context, ctx_files = (
            redcon_context(worktree, task, budget)
            if arm == "redcon"
            else naive_context(worktree, task, budget)
        )
        command = _command(_prompt(context, task))
        started = time.monotonic()
        proc = subprocess.run(command, cwd=str(worktree), stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=timeout)
        elapsed = round(time.monotonic() - started, 3)
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {**base, "error": "unparseable CLI output", "stderr_tail": proc.stderr[-500:]}
        result_text = data.get("result") or ""
        if transcript_dir is not None:
            transcript_dir.mkdir(parents=True, exist_ok=True)
            (transcript_dir / f"{task['sha'][:9]}-{arm}-r{repeat}.patch").write_text(
                result_text, encoding="utf-8"
            )
        overlap = diff_overlap(result_text, task)
        usage = data.get("modelUsage", {}).get(CANONICAL_MODEL, {})
        return {
            **base, **overlap,
            "budget": budget,
            "context_files": ctx_files,
            "changed_files": list(task["changed_files"]),
            "cost_usd": data.get("total_cost_usd"),
            "input_tokens": usage.get("inputTokens"),
            "cache_read_tokens": usage.get("cacheReadInputTokens"),
            "output_tokens": usage.get("outputTokens"),
            "elapsed_wall": elapsed,
        }
    except subprocess.TimeoutExpired:
        return {**base, "error": "timeout"}
    finally:
        import contextlib

        with contextlib.suppress(subprocess.CalledProcessError):
            _git(repo_path, "worktree", "remove", "--force", str(worktree))


def main() -> int:
    sys.path.insert(0, str(_REPO_ROOT))
    from corpus import read_tasks_jsonl  # noqa: PLC0415
    from repos import REPOS  # noqa: PLC0415
    from repos_heavy import REPOS_HEAVY  # noqa: PLC0415
    from runner import ensure_clone  # noqa: PLC0415

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=_HERE / "tasks-heavy.jsonl")
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache" / "redcon-agentic-heavy")
    parser.add_argument("--worktrees", type=Path, default=Path.home() / ".cache" / "redcon-oneshot-wt")
    parser.add_argument("--out-dir", type=Path, default=_HERE / "results" / "oneshot")
    parser.add_argument("--arms", default=",".join(ARMS))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    args = parser.parse_args()

    arms = tuple(a.strip() for a in args.arms.split(",") if a.strip())
    tasks = read_tasks_jsonl(args.tasks)
    if args.limit:
        tasks = tasks[: args.limit]
    specs = {s.name: s for s in (*REPOS, *REPOS_HEAVY)}
    repo_paths = {
        name: (_REPO_ROOT if name == "redcon" else ensure_clone(
            specs[name].name, specs[name].url, specs[name].ref, args.cache))
        for name in sorted({t["repo"] for t in tasks})
        if name in specs
    }

    out_path = args.out_dir / "records.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    counter = 0
    with out_path.open("a", encoding="utf-8") as handle:
        for task in tasks:
            if task["repo"] not in repo_paths:
                continue
            for repeat in range(args.repeats):
                for arm in arms:
                    counter += 1
                    try:
                        record = run_one(
                            task, arm, repeat,
                            repo_path=repo_paths[task["repo"]],
                            worktree=args.worktrees / f"wt-{counter}",
                            transcript_dir=args.out_dir / "transcripts",
                            timeout=args.timeout,
                        )
                    except Exception as exc:  # noqa: BLE001 - one bad run must not stop the pass
                        record = {"repo": task["repo"], "sha": task["sha"], "arm": arm,
                                  "repeat": repeat, "error": f"{type(exc).__name__}: {exc}"}
                    handle.write(json.dumps(record, sort_keys=True) + "\n")
                    handle.flush()
                    print(f"[{arm}] {record['repo']}/{record['sha'][:9]} r{repeat} "
                          f"file={record.get('file_overlap')} line={record.get('line_overlap')} "
                          f"parsed={record.get('parsed')} cost=${record.get('cost_usd')}")
    print(f"wrote records to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
