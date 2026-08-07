"""The large repositories the context-heavy corpus is pinned to.

Both are permissive (BSD-3-Clause) Python projects far larger than the small-repo
corpus - each is several million tokens of source, so a task that touches several
files across a couple of directories genuinely puts the agent's context under
pressure. Pinned to fixed SHAs so the corpus never shifts under a re-clone; cloned
into a cache by the builder, not vendored.
"""

from __future__ import annotations

from corpus import RepoSpec

REPOS_HEAVY = (
    RepoSpec(
        name="django",
        ref="4243ab11dc957fd14a1875e6b715ff5e6114a415",
        url="https://github.com/django/django",
    ),
    RepoSpec(
        name="sympy",
        ref="c0a595d78fb2a2c4b0dfa7f2ee720fde84918c6c",
        url="https://github.com/sympy/sympy",
    ),
)

# Heavy-corpus qualifying filters: multi-file, multi-directory, substantial diff.
HEAVY_FILTERS = {
    "min_files": 3,
    "max_files": 8,
    "min_dirs": 2,
    "min_diff_lines": 60,
    "max_diff_lines": 400,
}
