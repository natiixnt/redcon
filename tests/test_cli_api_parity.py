"""CLI vs Python API parity for plan, pack and report.

The CLI is a thin wrapper over ``RedconEngine``: ``redcon plan``/``pack`` write
the dict the engine returns, and ``redcon report`` renders the engine's summary.
These tests pin that contract so the two entry points cannot drift, comparing
the deterministic output on equivalent inputs.
"""

from __future__ import annotations

import json
from pathlib import Path

from redcon.cli import build_parser
from redcon.core.render import render_report_markdown
from redcon.engine import RedconEngine

# Fields that legitimately differ run to run or just echo the input path.
_VOLATILE_KEYS = {"generated_at", "timestamp", "run_id", "repo", "absolute_path"}


def _is_volatile(key: str) -> bool:
    return key in _VOLATILE_KEYS or key.endswith("_ms") or key.endswith("_seconds")


def _normalize(obj: object) -> object:
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items() if not _is_volatile(k)}
    if isinstance(obj, list):
        return [_normalize(v) for v in obj]
    return obj


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed(repo: Path) -> None:
    _write(
        repo / "auth" / "login.py",
        "from auth.session import make\n\n\ndef login(t):\n    return make(t)\n",
    )
    _write(repo / "auth" / "session.py", "def make(t):\n    return bool(t)\n")
    _write(repo / "tests" / "test_login.py", "def test_login():\n    assert True\n")


def _run_cli(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


def test_plan_parity(tmp_path: Path) -> None:
    api_repo = tmp_path / "api"
    cli_repo = tmp_path / "cli"
    _seed(api_repo)
    _seed(cli_repo)

    api = RedconEngine().plan(task="fix the login auth flow", repo=str(api_repo))

    out = tmp_path / "plan"
    assert (
        _run_cli(
            ["plan", "fix the login auth flow", "--repo", str(cli_repo), "--out-prefix", str(out)]
        )
        == 0
    )
    cli = json.loads(Path(f"{out}.json").read_text())

    assert _normalize(api) == _normalize(cli)


def test_pack_parity(tmp_path: Path) -> None:
    api_repo = tmp_path / "api"
    cli_repo = tmp_path / "cli"
    _seed(api_repo)
    _seed(cli_repo)

    api = RedconEngine().pack(task="fix the login auth flow", repo=str(api_repo), max_tokens=5000)

    out = tmp_path / "run"
    assert (
        _run_cli(
            [
                "pack",
                "fix the login auth flow",
                "--repo",
                str(cli_repo),
                "--max-tokens",
                "5000",
                "--out-prefix",
                str(out),
            ]
        )
        == 0
    )
    cli = json.loads(Path(f"{out}.json").read_text())

    # The deterministic content fingerprint must match across entry points.
    assert api["prompt_cache_key"] == cli["prompt_cache_key"]
    assert _normalize(api) == _normalize(cli)


def test_report_parity(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _seed(repo)
    # One shared artifact so both paths report on identical input.
    run_path = tmp_path / "run.json"
    _run_cli(
        [
            "pack",
            "fix the login auth flow",
            "--repo",
            str(repo),
            "--max-tokens",
            "5000",
            "--out-prefix",
            str(tmp_path / "run"),
        ]
    )
    assert run_path.exists()

    api_markdown = render_report_markdown(RedconEngine().report(run_path))

    md_out = tmp_path / "report.md"
    assert _run_cli(["report", str(run_path), "--out", str(md_out)]) == 0
    cli_markdown = md_out.read_text()

    assert api_markdown == cli_markdown
