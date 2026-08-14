# Copyright (c) 2026 Natalia Szczepanik. Licensed under FSL-1.1-MIT (see LICENSE).

"""Deterministic, task-independent repository brief.

A brief is a small map of a repository's shape - module geography, entry points,
test layout, and build/config conventions - built purely from scan, role, and
import-graph aggregates. It takes no task input and lists no per-task file
ranking: the same tree produces the same brief, and one brief serves every task
on the repo. That task independence is deliberate. Injecting a task-specific
ranked file list anchored the agent and hurt recall (the P-lite result); a brief
carries geography only, so it cannot anchor a change.

The output is capped to a small token budget so it is cheap to keep in context.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from redcon.config import RedconConfig, load_config
from redcon.core.tokens import estimate_tokens
from redcon.schemas.models import FileRecord
from redcon.scorers.import_graph import build_import_graph
from redcon.stages.workflow import run_scan_stage

# Conventional execution entry-point basenames (not build files, not test infra).
_ENTRYPOINT_NAMES = (
    "__main__.py",
    "main.py",
    "manage.py",
    "cli.py",
    "app.py",
    "wsgi.py",
    "asgi.py",
)
# Root build and config files, in the order they are reported when present.
_BUILD_FILES = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "tox.ini",
    "noxfile.py",
    "Makefile",
    "requirements.txt",
    "requirements-dev.txt",
    "package.json",
    "Cargo.toml",
    "go.mod",
    ".pre-commit-config.yaml",
    "conftest.py",
    "pytest.ini",
)
# Cap on how many package lines the geography section lists before summarizing.
_MAX_GEOGRAPHY_LINES = 24
# Default token ceiling for the whole brief.
DEFAULT_MAX_TOKENS = 2000


@dataclass(frozen=True)
class Brief:
    """A rendered repository brief and its provenance."""

    repo: str
    text: str
    tokens: int
    file_count: int
    truncated: bool


def _posix(path: str) -> PurePosixPath:
    return PurePosixPath(path.replace("\\", "/"))


def _top_component(path: str) -> str:
    parts = _posix(path).parts
    return parts[0] if parts else ""


def _main_package(prod_files: list[FileRecord]) -> str | None:
    """The top-level directory holding the most production source, if any.

    Ties break alphabetically so the choice is deterministic.
    """
    counts: Counter[str] = Counter()
    for record in prod_files:
        top = _top_component(record.path)
        if top and "." not in top:  # a directory, not a root-level file
            counts[top] += 1
    if not counts:
        return None
    best = max(sorted(counts), key=lambda name: counts[name])
    return best


def _files(n: int) -> str:
    return f"{n} file" if n == 1 else f"{n} files"


def _package_view(
    prod_files: list[FileRecord], package: str
) -> tuple[dict[str, list[tuple[str, ...]]], list[str]]:
    """Split *package* into subdirectories and direct module files.

    Returns (subdirs, direct_modules): subdirs maps a subdirectory name to the
    path-parts of the prod files beneath it; direct_modules is the module stems
    living directly in the package.
    """
    subdirs: dict[str, list[tuple[str, ...]]] = defaultdict(list)
    direct: list[str] = []
    for record in prod_files:
        parts = _posix(record.path).parts
        if len(parts) < 2 or parts[0] != package:
            continue
        if len(parts) == 2:
            direct.append(PurePosixPath(parts[1]).stem)
        else:
            subdirs[parts[1]].append(parts)
    return subdirs, direct


def _subdir_descriptor(paths_parts: list[tuple[str, ...]], limit: int = 4) -> str:
    """Immediate children of a subdirectory: grandchild directories keep a trailing
    slash, module files show their stem. Most common first, alphabetical in a tie."""
    counts: Counter[str] = Counter()
    for parts in paths_parts:
        # parts == (package, subdir, grandchild, ...)
        grandchild = parts[2]
        if len(parts) >= 4:
            counts[grandchild + "/"] += 1  # grandchild is a directory
        else:
            counts[PurePosixPath(grandchild).stem] += 1  # grandchild is a module file
    names = sorted(counts, key=lambda name: (-counts[name], name))[:limit]
    extra = len(counts) - len(names)
    tail = f", +{extra} more" if extra > 0 else ""
    return ", ".join(names) + tail if names else ""


def _geography_lines(prod_files: list[FileRecord], package: str | None) -> tuple[list[str], bool]:
    lines: list[str] = []
    truncated = False
    if package:
        subdirs, direct = _package_view(prod_files, package)
        ordered = sorted(subdirs, key=lambda name: (-len(subdirs[name]), name))
        shown = ordered[:_MAX_GEOGRAPHY_LINES]
        truncated = len(ordered) > len(shown)
        for child in sorted(shown):
            parts_list = subdirs[child]
            desc = _subdir_descriptor(parts_list)
            suffix = f": {desc}" if desc else ""
            lines.append(f"- `{package}/{child}/` ({_files(len(parts_list))}){suffix}")
        if truncated:
            lines.append(f"- ... and {len(ordered) - len(shown)} more `{package}/` subpackages")
        if direct:
            mods = ", ".join(sorted(set(direct)))
            lines.append(f"- `{package}/` top-level modules: {mods}")
    else:
        # No dominant package: list top-level directories instead.
        tops: Counter[str] = Counter()
        for record in prod_files:
            top = _top_component(record.path)
            if top and "." not in top:
                tops[top] += 1
        ordered = sorted(tops, key=lambda name: (-tops[name], name))[:_MAX_GEOGRAPHY_LINES]
        for top in sorted(ordered):
            lines.append(f"- `{top}/` ({_files(tops[top])})")
    return lines, truncated


def _entrypoints(files: list[FileRecord]) -> list[str]:
    # Production entry points only, so example and generated mains do not crowd out
    # the real ones.
    found: list[str] = []
    for record in files:
        if record.role == "prod" and _posix(record.path).name in _ENTRYPOINT_NAMES:
            found.append(record.path)
    return sorted(set(found))


def _test_layout(files: list[FileRecord]) -> list[str]:
    test_files = [f for f in files if f.role == "test"]
    if not test_files:
        return ["- no dedicated test files detected"]
    top_dirs: Counter[str] = Counter()
    for record in test_files:
        top_dirs[_top_component(record.path)] += 1
    lines = [f"- {_files(len(test_files))} total"]
    for top in sorted(top_dirs, key=lambda name: (-top_dirs[name], name))[:6]:
        label = f"`{top}/`" if top and "." not in top else "(repository root)"
        lines.append(f"- {label}: {_files(top_dirs[top])}")
    return lines


def _build_config(files: list[FileRecord]) -> list[str]:
    present = {_posix(f.path).name for f in files if len(_posix(f.path).parts) == 1}
    lines = [f"- `{name}`" for name in _BUILD_FILES if name in present]
    return lines or ["- no standard build or config files found at the repository root"]


def _render(
    repo_name: str,
    file_count: int,
    lang_summary: str,
    geography: list[str],
    entrypoints: list[str],
    test_layout: list[str],
    build_config: list[str],
    import_edges: int,
) -> str:
    parts = [
        f"# Repository brief: {repo_name}",
        "",
        (
            f"Task-independent map of {file_count} scanned files ({lang_summary}), "
            f"{import_edges} internal import links. Geography only, no per-change file list."
        ),
        "",
        "## Module geography",
        *geography,
        "",
        "## Entry points",
        *([f"- `{p}`" for p in entrypoints] or ["- no conventional entry-point files detected"]),
        "",
        "## Test layout",
        *test_layout,
        "",
        "## Build and config",
        *build_config,
    ]
    return "\n".join(parts) + "\n"


def _language_summary(files: list[FileRecord], limit: int = 3) -> str:
    exts: Counter[str] = Counter()
    for record in files:
        if record.extension:
            exts[record.extension] += 1
    if not exts:
        return "no recognized source"
    top = sorted(exts, key=lambda ext: (-exts[ext], ext))[:limit]
    return ", ".join(f"{ext} x{exts[ext]}" for ext in top)


def build_brief(
    repo: Path | str,
    config: RedconConfig | None = None,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Brief:
    """Build a deterministic, task-independent brief for *repo*.

    The same tree and config produce byte-identical output. The brief is trimmed
    to stay within *max_tokens*; when geography is dropped to fit, the result is
    marked truncated.
    """
    repo_path = Path(repo)
    cfg = config or load_config(repo_path)
    files = run_scan_stage(repo_path, cfg)

    prod_files = [f for f in files if f.role == "prod"]
    package = _main_package(prod_files)
    geography, geo_truncated = _geography_lines(prod_files, package)
    entrypoints = _entrypoints(files)
    test_layout = _test_layout(files)
    build_config = _build_config(files)
    lang_summary = _language_summary(files)
    graph = build_import_graph(files, set(_ENTRYPOINT_NAMES))
    import_edges = sum(len(v) for v in graph.outgoing.values())

    repo_name = repo_path.resolve().name

    def render(geo: list[str]) -> str:
        return _render(
            repo_name,
            len(files),
            lang_summary,
            geo,
            entrypoints,
            test_layout,
            build_config,
            import_edges,
        )

    text = render(geography)
    truncated = geo_truncated
    # Trim geography from the tail until the brief fits the token ceiling.
    while estimate_tokens(text) > max_tokens and len(geography) > 1:
        geography = geography[:-1]
        truncated = True
        text = render(geography + [f"- ... geography trimmed to fit {max_tokens} tokens"])

    return Brief(
        repo=repo_name,
        text=text,
        tokens=estimate_tokens(text),
        file_count=len(files),
        truncated=truncated,
    )
