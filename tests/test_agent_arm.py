"""Tests for the agent-in-the-loop arm (benchmarks/agentic/agent_arm.py).

These cover the pure plumbing - command construction, MCP config generation,
result parsing, and the edited-files metric - without ever spawning the Claude
CLI, so they are deterministic and free. The live runs are exercised separately
and never in CI.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_HARNESS = Path(__file__).resolve().parent.parent / "benchmarks" / "agentic"
sys.path.insert(0, str(_HARNESS))

import agent_arm  # noqa: E402


def _task() -> dict:
    return {
        "repo": "demo",
        "sha": "deadbeef",
        "parent_sha": "deadbeef^",
        "changed_files": ["src/retry.py"],
        "phrasings": {
            "precise": "add retry with backoff to the client",
            "medium": "add retry with backoff",
            "vague": "improve the src area",
        },
    }


def test_write_mcp_configs_isolates_baseline(tmp_path: Path) -> None:
    redcon_root = Path("/repo")
    configs = agent_arm.write_mcp_configs(
        tmp_path, venv_python="/venv/bin/python", redcon_root=redcon_root
    )
    redcon = json.loads(configs["redcon"].read_text(encoding="utf-8"))
    empty = json.loads(configs["baseline"].read_text(encoding="utf-8"))
    assert "redcon" in redcon["mcpServers"]
    # str(Path(...)) so the assertion holds on Windows too (backslash separator).
    assert redcon["mcpServers"]["redcon"]["env"]["PYTHONPATH"] == str(redcon_root)
    # The baseline arm must see no MCP server at all.
    assert empty["mcpServers"] == {}


def test_build_command_differs_only_by_config(tmp_path: Path) -> None:
    configs = agent_arm.write_mcp_configs(
        tmp_path, venv_python="/venv/bin/python", redcon_root=Path("/repo")
    )
    prompt = agent_arm.agent_prompt(_task())
    redcon_cmd = agent_arm.build_command("redcon", prompt, configs["redcon"])
    base_cmd = agent_arm.build_command("baseline", prompt, configs["baseline"])

    for cmd in (redcon_cmd, base_cmd):
        assert "-p" in cmd
        assert "--strict-mcp-config" in cmd
        assert cmd[cmd.index("--model") + 1] == agent_arm.MODEL
        assert cmd[cmd.index("--max-turns") + 1] == str(agent_arm.MAX_TURNS)
        assert cmd[cmd.index("--permission-mode") + 1] == "bypassPermissions"
    # The only difference between arms is which MCP config is loaded.
    assert redcon_cmd[redcon_cmd.index("--mcp-config") + 1] == str(configs["redcon"])
    assert base_cmd[base_cmd.index("--mcp-config") + 1] == str(configs["baseline"])


def test_agent_prompt_is_arm_independent() -> None:
    prompt = agent_arm.agent_prompt(_task())
    assert "add retry with backoff to the client" in prompt
    assert "redcon" not in prompt.lower()  # no arm-specific hint biases the run


def test_parse_result_extracts_usage_and_cost() -> None:
    stdout = json.dumps(
        {
            "is_error": False,
            "terminal_reason": "completed",
            "num_turns": 7,
            "total_cost_usd": 0.42,
            "duration_ms": 12345,
            "duration_api_ms": 11000,
            "permission_denials": [],
            "result": "Added retry with backoff.",
            "modelUsage": {
                "claude-sonnet-5": {
                    "inputTokens": 120,
                    "outputTokens": 900,
                    "cacheReadInputTokens": 50000,
                    "cacheCreationInputTokens": 8000,
                }
            },
        }
    )
    parsed = agent_arm._parse_result(stdout)
    assert parsed["is_error"] is False
    assert parsed["num_turns"] == 7
    assert parsed["cost_usd"] == 0.42
    assert parsed["input_tokens"] == 120
    assert parsed["output_tokens"] == 900
    assert parsed["cache_read_tokens"] == 50000
    assert parsed["cache_creation_tokens"] == 8000
    assert parsed["result_summary"] == "Added retry with backoff."


def test_files_edited_reports_modified_added_and_renamed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.email=t@e", "-c", "user.name=t", *args],
            check=True,
            capture_output=True,
        )

    git("init", "-q")
    (repo / "keep.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "old.py").write_text("y = 2\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "init")

    (repo / "keep.py").write_text("x = 2\n", encoding="utf-8")  # modified
    (repo / "new.py").write_text("z = 3\n", encoding="utf-8")  # added
    git("mv", "old.py", "renamed.py")  # renamed

    edited = agent_arm._files_edited(repo)
    assert "keep.py" in edited
    assert "new.py" in edited
    assert "renamed.py" in edited  # the destination side of the rename


def test_file_hits_is_recall_of_changed_files() -> None:
    assert agent_arm._file_hits(["a.py", "b.py"], ["a.py", "c.py"]) == 0.5
    assert agent_arm._file_hits(["a.py"], ["a.py"]) == 1.0
    assert agent_arm._file_hits([], ["a.py"]) == 0.0


def test_completed_keys_reads_only_successful_runs(tmp_path: Path) -> None:
    records = tmp_path / "records.jsonl"
    records.write_text(
        "\n".join(
            json.dumps(r)
            for r in [
                {"sha": "a", "arm": "redcon", "seed": 0, "num_turns": 4},
                {"sha": "a", "arm": "baseline", "seed": 0, "error": "timeout"},
                {"sha": "b", "arm": "redcon", "seed": 1, "num_turns": 7},
                {"sha": "c", "arm": "redcon", "seed": 0, "dry_run": True},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    done = agent_arm.completed_keys(records)
    assert done == {("a", "redcon", 0), ("b", "redcon", 1)}
    assert agent_arm.completed_keys(tmp_path / "missing.jsonl") == set()


def test_select_pilot_tasks_is_stratified_and_deterministic() -> None:
    tasks = []
    for repo in ("alpha", "beta"):
        for size in range(1, 21):  # 20 tasks/repo, spanning small to large
            tasks.append(
                {
                    "repo": repo,
                    "sha": f"{repo}{size:02d}",
                    "changed_files": ["f.py"],
                    "hunk_names": {"f.py": [{"range": [1, size], "symbol": ""}]},
                }
            )

    picked = agent_arm.select_pilot_tasks(tasks, per_repo=4)
    assert len(picked) == 8  # 4 per repo x 2 repos
    per_repo = {"alpha": [], "beta": []}
    for task in picked:
        per_repo[task["repo"]].append(agent_arm._task_size(task))
    for sizes in per_repo.values():
        assert len(sizes) == 4
        assert sizes == sorted(sizes)  # spans small to large
        assert min(sizes) < max(sizes)  # genuinely spread, not all the same size
    # Deterministic across calls.
    assert [t["sha"] for t in agent_arm.select_pilot_tasks(tasks, per_repo=4)] == [
        t["sha"] for t in picked
    ]


def test_looks_rate_limited_detects_usage_signals() -> None:
    assert agent_arm._looks_rate_limited({"is_error": True, "error": "HTTP 429 rate limit"})
    assert agent_arm._looks_rate_limited({"terminal_reason": "usage limit reached"})
    assert agent_arm._looks_rate_limited({"stderr_tail": "server overloaded, retry later"})
    assert not agent_arm._looks_rate_limited({"is_error": False, "result_summary": "done"})
    assert not agent_arm._looks_rate_limited({"error": "timeout"})


def test_run_one_dry_run_builds_command_without_spawning(tmp_path: Path) -> None:
    configs = agent_arm.write_mcp_configs(
        tmp_path, venv_python=sys.executable, redcon_root=Path("/repo")
    )
    record = agent_arm.run_one(
        _task(),
        "redcon",
        0,
        repo_path=tmp_path,
        worktree=tmp_path / "wt",
        mcp_config=configs["redcon"],
        dry_run=True,
    )
    assert record["dry_run"] is True
    assert record["arm"] == "redcon"
    assert "--strict-mcp-config" in record["command"]
    assert not (tmp_path / "wt").exists()  # nothing was checked out
