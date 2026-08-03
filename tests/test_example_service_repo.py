"""Pin the example service repo's documented output so it cannot drift.

`examples/service-repo/README.md` shows a fixed ranking and a validating pack.
These tests reproduce those commands against a temp copy of the repo (so the
committed example is never touched by scan/cache artifacts) and assert the
documented results.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from redcon.engine import RedconEngine
from redcon.validation import validate_artifact

_EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "service-repo"
_TASK = "add an order cancellation endpoint"


def _copy(dest: Path) -> Path:
    shutil.copytree(_EXAMPLE, dest)
    return dest


def test_example_repo_ranking_matches_readme(tmp_path: Path) -> None:
    repo = _copy(tmp_path / "repo")
    data = RedconEngine().plan(task=_TASK, repo=str(repo))
    paths = [r["path"] for r in data["ranked_files"]]
    assert paths[:5] == [
        "src/orders/api.py",
        "src/orders/repository.py",
        "src/orders/service.py",
        "src/orders/main.py",
        "src/orders/models.py",
    ]


def test_example_repo_pack_validates(tmp_path: Path) -> None:
    repo = _copy(tmp_path / "repo")
    run = RedconEngine().pack(task=_TASK, repo=str(repo), max_tokens=8000)
    # The packed artifact conforms to the published run schema.
    assert validate_artifact(run) == []
    assert run["files_skipped"] == []  # everything fits the 8000-token budget


def test_example_repo_pack_is_deterministic(tmp_path: Path) -> None:
    first = RedconEngine().pack(task=_TASK, repo=str(_copy(tmp_path / "a")), max_tokens=8000)
    second = RedconEngine().pack(task=_TASK, repo=str(_copy(tmp_path / "b")), max_tokens=8000)
    assert first["prompt_cache_key"] == second["prompt_cache_key"]
