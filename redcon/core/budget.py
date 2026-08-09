"""Scale the default pack budget by repository size.

The default budget (30k) under-covers very large repositories: the agentic
coverage sweep measured pack file-hits rising from 0.36 at 12k to 0.90 at 120k on
a 5-7M-token repo. So when the user does not pass an explicit budget, the default
grows step-wise with the scanned repository size, and an explicit budget that is
small for the repository's size earns a warning.

Only the top step (repositories above ~3M tokens use 120k, which the sweep
measured at ~0.90 coverage) is directly measured. The middle steps interpolate
between the measured ends; they are not four separate measurements. Small
repositories (<= 200k tokens) are unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from redcon.schemas.models import DEFAULT_MAX_TOKENS

if TYPE_CHECKING:
    from redcon.config import RedconConfig

# (repository-token ceiling, default budget). Ascending; the last row is the
# floor for anything larger.
_BUDGET_STEPS: tuple[tuple[int, int], ...] = (
    (200_000, DEFAULT_MAX_TOKENS),  # small repos: unchanged
    (1_000_000, 45_000),
    (3_000_000, 75_000),
)
_LARGE_REPO_BUDGET = 120_000


def default_budget_for_repo_tokens(repo_tokens: int) -> int:
    """The default pack budget for a repository of *repo_tokens* tokens."""
    for ceiling, budget in _BUDGET_STEPS:
        if repo_tokens <= ceiling:
            return budget
    return _LARGE_REPO_BUDGET


def coverage_warning(repo_tokens: int, budget: int) -> str | None:
    """A warning if *budget* is below the recommended default for the repo size.

    Only fires for repositories large enough that the default grows above the
    baseline (> 200k tokens); a small budget on a small repo is the user's call
    and never warns.
    """
    recommended = default_budget_for_repo_tokens(repo_tokens)
    if recommended <= DEFAULT_MAX_TOKENS or budget >= recommended:
        return None
    return (
        f"redcon: budget {budget:,} tokens may under-cover this repository "
        f"(~{repo_tokens:,} tokens); ~{recommended:,} is recommended for its size. "
        "Coverage rises with budget on large repositories."
    )


def estimate_repo_tokens(repo: Path, config: RedconConfig | None = None) -> int:
    """A cheap estimate of the repository's total tokens, from the scan index.

    Uses cached file sizes (bytes / 4), so it is fast on a warm index and does not
    read file contents. This is the same basis used to size the sweep repos, so
    it stays consistent with the thresholds above.
    """
    from redcon.scanners.incremental import refresh_scan_index  # noqa: PLC0415

    kwargs: dict = {}
    if config is not None:
        scan = config.scan
        kwargs = {
            "max_file_size_bytes": scan.max_file_size_bytes,
            "preview_chars": scan.preview_chars,
            "include_globs": scan.include_globs,
            "ignore_globs": scan.ignore_globs,
            "ignore_dirs": scan.ignore_dirs,
            "binary_extensions": scan.binary_extensions,
            "max_file_count": scan.max_file_count,
            "exclude_secrets": scan.exclude_secrets,
        }
    result = refresh_scan_index(Path(repo), **kwargs)
    return sum(record.size_bytes for record in result.records) // 4
