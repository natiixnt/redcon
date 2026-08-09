"""Tests for the repo-size-scaled default budget."""

from __future__ import annotations

from pathlib import Path

from redcon.core.budget import (
    coverage_warning,
    default_budget_for_repo_tokens,
    estimate_repo_tokens,
)
from redcon.schemas.models import DEFAULT_MAX_TOKENS


def test_small_repos_keep_the_default_budget():
    # Repositories at or below 200k tokens are unchanged.
    assert default_budget_for_repo_tokens(0) == DEFAULT_MAX_TOKENS
    assert default_budget_for_repo_tokens(50_000) == DEFAULT_MAX_TOKENS
    assert default_budget_for_repo_tokens(200_000) == DEFAULT_MAX_TOKENS


def test_budget_grows_stepwise_with_repo_size():
    assert default_budget_for_repo_tokens(500_000) == 45_000
    assert default_budget_for_repo_tokens(2_000_000) == 75_000
    assert default_budget_for_repo_tokens(6_000_000) == 120_000
    # Monotonic non-decreasing across the range.
    sizes = [0, 200_000, 200_001, 1_000_000, 1_000_001, 3_000_000, 3_000_001, 10_000_000]
    budgets = [default_budget_for_repo_tokens(s) for s in sizes]
    assert budgets == sorted(budgets)


def test_warning_only_when_budget_is_below_the_recommendation():
    # A default-sized budget on a large repo is under the recommendation.
    warning = coverage_warning(6_000_000, DEFAULT_MAX_TOKENS)
    assert warning is not None
    assert "under-cover" in warning
    assert "120,000" in warning
    # At or above the recommendation there is no warning.
    assert coverage_warning(6_000_000, 120_000) is None
    # Small repos never warn - even a tiny budget is the user's call.
    assert coverage_warning(50_000, DEFAULT_MAX_TOKENS) is None
    assert coverage_warning(50_000, 5_000) is None


def test_estimate_repo_tokens_counts_from_the_scan(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\n" * 100, encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "b.py").write_text("y = 2\n" * 100, encoding="utf-8")
    tokens = estimate_repo_tokens(tmp_path)
    # Two ~600-byte files, so roughly (1200 bytes / 4) = ~300 tokens; allow slack.
    assert 100 <= tokens <= 1000
