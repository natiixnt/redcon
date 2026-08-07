"""Build a deterministic task corpus from git history.

A task is a real commit: the parent-state repository is what a context tool
sees, and the files and line ranges the commit changed are the ground truth it
should surface. Each task carries three phrasings of the same intent, so the
evaluation can measure how sensitive selection is to how a task is described:

- precise: the commit subject, cleaned of its conventional-commit prefix.
- medium:  the subject with file names and symbol names stripped out.
- vague:   a template naming only the area of the tree that changed.

The corpus is written to ``tasks.jsonl`` and pinned in the repository so runs
are reproducible without re-walking history. Nothing about a commit's own
diff can leak into selection: tools are always run at the parent state.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

# The source extensions a task may touch. Ground truth and the selection
# universe use the same set, so file coverage is well defined.
SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx"}

# Subjects of these commit types describe the code they change; docs/chore/ci
# subjects name a process, not code, so they make noisy tasks.
TASKLIKE_TYPES = {"feat", "fix", "perf", "refactor"}
_CONVENTIONAL_PREFIX = re.compile(r"^([a-z]+)(\([^)]*\))?!?:\s*")

# The maximum combined added+deleted source lines a task may change. Larger
# commits are sprawling refactors whose "intent" is diffuse.
MAX_DIFF_LINES = 400


@dataclass(frozen=True)
class RepoSpec:
    """A repository to mine, pinned to a fixed revision for reproducibility."""

    name: str
    ref: str  # tag or commit SHA the corpus is pinned to
    url: str = ""  # remote to clone when not already present; empty = local only


@dataclass(frozen=True)
class Hunk:
    """A changed region, addressed in the parent-state file."""

    start: int
    end: int
    symbol: str = ""


@dataclass(frozen=True)
class Task:
    """One benchmark task derived from a single commit."""

    repo: str
    sha: str
    parent_sha: str
    changed_files: tuple[str, ...]
    hunk_names: dict[str, list[dict[str, object]]]
    phrasings: dict[str, str]

    def to_json(self) -> dict[str, object]:
        return asdict(self)


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",  # some diffs carry non-utf-8 bytes; never crash mining
        check=True,
    )
    return proc.stdout


def is_source_path(path: str) -> bool:
    if any(part.startswith(".") for part in path.split("/")[:-1]):
        return False
    return Path(path).suffix.lower() in SOURCE_EXTS


def _changed_source_files(repo: Path, sha: str) -> list[str]:
    """Return the modified/renamed/deleted source files, addressed at the parent.

    Added files did not exist at the parent state, so no selection tool could
    have picked them; they are excluded from the ground truth.
    """
    name_status = _git(repo, "show", "--name-status", "--format=", sha)
    files: set[str] = set()
    for row in name_status.splitlines():
        parts = row.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        if not status.startswith(("M", "D", "R")):
            continue
        path = parts[1]  # for renames this is the old (parent) path
        if is_source_path(path):
            files.add(path)
    return sorted(files)


_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@\s*(.*)$")
_SYMBOL = re.compile(r"(?:def|class|function|const|func)\s+([A-Za-z_]\w*)")


def _hunks_for_file(repo: Path, sha: str, path: str) -> list[Hunk]:
    """Parent-state changed line ranges for one file, with any enclosing symbol."""
    diff = _git(repo, "show", "--format=", "--unified=0", sha, "--", path)
    hunks: list[Hunk] = []
    for line in diff.splitlines():
        match = _HUNK_HEADER.match(line)
        if not match:
            continue
        start = int(match.group(1))
        count = int(match.group(2)) if match.group(2) is not None else 1
        # A pure insertion reports count 0 at the line it follows; treat it as a
        # single-line region so containment still has something to test.
        end = start + count - 1 if count > 0 else start
        symbol_match = _SYMBOL.search(match.group(3) or "")
        symbol = symbol_match.group(1) if symbol_match else ""
        hunks.append(Hunk(start=start, end=max(start, end), symbol=symbol))
    return hunks


def _diff_line_count(repo: Path, sha: str, files: list[str]) -> int:
    """Combined added+deleted lines across the given files."""
    if not files:
        return 0
    numstat = _git(repo, "show", "--numstat", "--format=", sha, "--", *files)
    total = 0
    for row in numstat.splitlines():
        parts = row.split("\t")
        if len(parts) < 2:
            continue
        added, deleted = parts[0], parts[1]
        if added == "-" or deleted == "-":  # binary file
            continue
        total += int(added) + int(deleted)
    return total


def _precise(subject: str) -> str:
    return _CONVENTIONAL_PREFIX.sub("", subject).strip()


def _medium(precise: str, symbols: set[str]) -> str:
    """Strip file names and symbol names so only the intent remains."""
    text = re.sub(r"`[^`]*`", " ", precise)
    text = re.sub(r"\b[\w./-]+\.(?:py|ts|tsx|js|jsx|md|toml|json|yaml|yml)\b", " ", text)
    text = re.sub(r"\b[\w-]+/[\w./-]+\b", " ", text)
    for symbol in sorted(symbols, key=len, reverse=True):
        if symbol:
            text = re.sub(rf"\b{re.escape(symbol)}\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -:,.")
    return text or precise


def _vague(changed_files: list[str]) -> str:
    """Name only the area of the tree that changed."""
    areas: list[str] = []
    for path in changed_files:
        parts = path.split("/")
        area = parts[-2] if len(parts) >= 2 else Path(parts[0]).stem
        areas.append(area)
    if not areas:
        return "improve the codebase"
    # Deterministic tie-break: most common area, then alphabetical.
    counts = Counter(areas)
    top = max(counts, key=lambda a: (counts[a], a))
    return f"improve the {top} area"


def build_tasks(
    repo: Path,
    repo_name: str,
    *,
    rev: str = "HEAD",
    max_tasks: int = 200,
    min_files: int = 1,
    max_files: int = 8,
    min_diff_lines: int = 0,
    max_diff_lines: int = MAX_DIFF_LINES,
    min_dirs: int = 1,
) -> list[Task]:
    """Walk history of *rev* and turn qualifying commits into tasks.

    A commit qualifies when: it is not a merge; its subject describes code
    (task-like conventional type, or no conventional prefix at all); it changed
    between ``min_files`` and ``max_files`` existing source files spanning at
    least ``min_dirs`` directories; and its source diff is in
    ``[min_diff_lines, max_diff_lines)`` lines. The defaults reproduce the
    original small-repo corpus; the context-heavy corpus tightens the lower
    bounds so tasks actually spread across a large tree.
    """
    tasks: list[Task] = []
    log = _git(repo, "log", rev, "--no-merges", "--format=%H|%s")
    for line in log.splitlines():
        sha, _, subject = line.partition("|")
        prefix = _CONVENTIONAL_PREFIX.match(subject)
        if prefix and prefix.group(1) not in TASKLIKE_TYPES:
            continue  # docs/chore/ci/style/test/build/release are not tasks
        precise = _precise(subject)
        if len(precise) < 15:
            continue  # "wip", "fix bug" make meaningless tasks

        changed = _changed_source_files(repo, sha)
        if not (min_files <= len(changed) <= max_files):
            continue
        if len({str(Path(p).parent) for p in changed}) < min_dirs:
            continue  # too localized: does not exercise a large tree
        diff_lines = _diff_line_count(repo, sha, changed)
        if not (min_diff_lines <= diff_lines < max_diff_lines):
            continue

        hunk_names: dict[str, list[dict[str, object]]] = {}
        symbols: set[str] = set()
        for path in changed:
            hunks = _hunks_for_file(repo, sha, path)
            hunk_names[path] = [
                {"range": [h.start, h.end], "symbol": h.symbol} for h in hunks
            ]
            symbols.update(h.symbol for h in hunks if h.symbol)

        tasks.append(
            Task(
                repo=repo_name,
                sha=sha,
                parent_sha=f"{sha}^",
                changed_files=tuple(changed),
                hunk_names=hunk_names,
                phrasings={
                    "precise": precise,
                    "medium": _medium(precise, symbols),
                    "vague": _vague(changed),
                },
            )
        )
        if len(tasks) >= max_tasks:
            break
    return tasks


def write_tasks_jsonl(tasks: list[Task], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for task in tasks:
            handle.write(json.dumps(task.to_json(), sort_keys=True) + "\n")


def read_tasks_jsonl(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
