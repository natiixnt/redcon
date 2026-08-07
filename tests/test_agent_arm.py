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


def test_arms_map_to_configs_and_guidance() -> None:
    # A and Ag use the redcon server; B uses the empty one. Only Ag is guided.
    assert agent_arm.ARM_SPECS["redcon"] == {"mcp": "redcon", "guided": False}
    assert agent_arm.ARM_SPECS["redcon_guided"] == {"mcp": "redcon", "guided": True}
    assert agent_arm.ARM_SPECS["baseline"] == {"mcp": "baseline", "guided": False}
    assert set(agent_arm.ARMS) == {"redcon", "redcon_guided", "baseline"}


def test_build_command_uses_stream_json(tmp_path: Path) -> None:
    configs = agent_arm.write_mcp_configs(
        tmp_path, venv_python="/venv/bin/python", redcon_root=Path("/repo")
    )
    cmd = agent_arm.build_command("a prompt", configs["redcon"])
    assert "-p" in cmd
    assert "--strict-mcp-config" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in cmd  # required for stream-json
    assert cmd[cmd.index("--model") + 1] == agent_arm.MODEL
    assert cmd[cmd.index("--max-turns") + 1] == str(agent_arm.MAX_TURNS)
    assert cmd[cmd.index("--mcp-config") + 1] == str(configs["redcon"])


def test_agent_prompt_guidance_and_phrasing() -> None:
    plain = agent_arm.agent_prompt(_task(), "precise")
    assert "add retry with backoff to the client" in plain
    assert "redcon" not in plain.lower()  # arm A carries no hint
    guided = agent_arm.agent_prompt(_task(), "precise", guided=True)
    assert guided.endswith(agent_arm.GUIDANCE)  # arm Ag appends exactly one line
    assert "add retry with backoff to the client" in guided
    medium = agent_arm.agent_prompt(_task(), "medium")
    assert "add retry with backoff" in medium and "to the client" not in medium


def test_parse_stream_extracts_metrics_and_tool_counts() -> None:
    stream = "\n".join(
        json.dumps(e)
        for e in [
            {"type": "system", "subtype": "init"},
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash"}]}},
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "name": "mcp__redcon__redcon_rank"}]},
            },
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash"}]}},
            {
                "type": "result",
                "is_error": False,
                "num_turns": 7,
                "total_cost_usd": 0.42,
                "result": "done",
                "modelUsage": {
                    "claude-sonnet-5": {
                        "inputTokens": 120,
                        "outputTokens": 900,
                        "cacheReadInputTokens": 50000,
                        "cacheCreationInputTokens": 8000,
                    }
                },
            },
        ]
    )
    metrics, counts = agent_arm.parse_stream(stream)
    assert metrics["num_turns"] == 7
    assert metrics["cost_usd"] == 0.42
    assert metrics["input_tokens"] == 120
    assert metrics["result_summary"] == "done"
    assert counts == {"Bash": 2, "mcp__redcon__redcon_rank": 1}
    assert agent_arm._redcon_calls(counts) == 1


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
                {"sha": "a", "arm": "redcon", "phrasing": "precise", "repeat": 0, "num_turns": 4},
                {"sha": "a", "arm": "baseline", "phrasing": "precise", "repeat": 0, "error": "t"},
                {"sha": "b", "arm": "redcon", "phrasing": "medium", "repeat": 1, "num_turns": 7},
                {"sha": "c", "arm": "redcon", "phrasing": "precise", "repeat": 0, "dry_run": True},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    done = agent_arm.completed_keys(records)
    # Phrasing is part of the key, so precise and medium runs never collide.
    assert done == {("a", "redcon", "precise", 0), ("b", "redcon", "medium", 1)}
    assert agent_arm.completed_keys(tmp_path / "missing.jsonl") == set()


def test_select_pilot_tasks_covers_strata_and_repos_evenly() -> None:
    tasks = []
    for repo in ("alpha", "beta", "gamma"):
        for size in range(1, 31):  # 30 tasks/repo spanning small to large
            tasks.append(
                {
                    "repo": repo,
                    "sha": f"{repo}{size:02d}",
                    "changed_files": ["f.py"],
                    "hunk_names": {"f.py": [{"range": [1, size], "symbol": ""}]},
                }
            )

    picked = agent_arm.select_pilot_tasks(tasks, per_stratum=4)
    assert len(picked) == 12
    strata = [t["stratum"] for t in picked]
    repos = [t["repo"] for t in picked]
    # 4 per size stratum, and the three repos evenly represented across the 12.
    assert all(strata.count(name) == 4 for name in agent_arm.STRATA)
    assert all(repos.count(repo) == 4 for repo in ("alpha", "beta", "gamma"))
    # Large tasks are genuinely larger than small ones.
    size_by = {name: [] for name in agent_arm.STRATA}
    for task in picked:
        size_by[task["stratum"]].append(agent_arm._task_size(task))
    assert max(size_by["small"]) < min(size_by["large"])
    # Deterministic across calls.
    assert [t["sha"] for t in agent_arm.select_pilot_tasks(tasks)] == [t["sha"] for t in picked]


def test_read_task_list_and_select_by_shas(tmp_path: Path) -> None:
    listing = tmp_path / "pilot-tasks.txt"
    listing.write_text(
        "# a comment\n\nsha1  # small alpha\nsha3 trailing junk\n",
        encoding="utf-8",
    )
    assert agent_arm.read_task_list(listing) == ["sha1", "sha3"]
    tasks = [{"sha": "sha1"}, {"sha": "sha2"}, {"sha": "sha3"}]
    picked = agent_arm._select_by_shas(tasks, ["sha3", "sha1", "missing"])
    assert [t["sha"] for t in picked] == ["sha3", "sha1"]  # order follows the list


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
        "redcon_guided",
        0,
        phrasing="precise",
        repo_path=tmp_path,
        worktree=tmp_path / "wt",
        mcp_config=configs["redcon"],
        dry_run=True,
    )
    assert record["dry_run"] is True
    assert record["arm"] == "redcon_guided"
    assert record["phrasing"] == "precise"
    assert record["guided"] is True
    # The guided arm's prompt carries the guidance line in the command.
    assert any(agent_arm.GUIDANCE in part for part in record["command"])
    assert "--strict-mcp-config" in record["command"]
    assert not (tmp_path / "wt").exists()  # nothing was checked out
