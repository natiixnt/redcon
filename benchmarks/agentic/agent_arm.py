"""Agent-in-the-loop arm: run the Claude Code CLI headless on each task, with
and without redcon, and record what each run cost.

Layer 2 of the evaluation. For every task x arm x repeat this checks out the
commit's parent state in a git worktree and runs the CLI headless (``-p``,
model sonnet, capped turns) to implement the change the task describes. Arm
``redcon`` exposes the redcon MCP server (rank/compress/budget/...); arm
``baseline`` runs with an empty MCP config, so it has only the built-in
filesystem tools. Each run records the token usage, list-price cost, turn count
and wall-clock time the CLI reports, plus which files the agent edited versus
the files the real commit changed.

Pre-registered hypothesis
-------------------------
An MCP server adds a roughly fixed per-session cost: its tool schemas sit in the
cached context whether or not the agent calls them. So redcon is expected to be
roughly neutral on small, well-localized tasks (where the baseline agent finds
the files quickly and redcon's schema overhead is not repaid) and to gain on
context-heavy tasks (where the baseline agent must read many or large files that
redcon can rank and compress). The pilot therefore covers the diff-size spectrum
(4 small / 4 medium / 4 large, by global terciles, spread across repos) and
reports per stratum, so the result shows where the product pays and where it is
a wash rather than claiming a blanket win.

Note on repeats: ``--repeats`` runs each task/arm N times. These are repetitions
to gauge run-to-run variance, not RNG seeds; the CLI exposes no seed, so this is
not a controlled-randomness knob and is named ``repeat`` in the records to keep
that honest.

Unlike layer 1 this arm is not deterministic (the model is stochastic) and it
draws on subscription usage, so it is run deliberately and never in CI. The
dollar figures are the CLI's list-price accounting, a reported metric, not a
per-call charge on this account.

    # small-repo pilot (night 1):
    python benchmarks/agentic/agent_arm.py --pilot
    # context-heavy night 2, pass 1 (arms A and B, precise):
    python benchmarks/agentic/agent_arm.py --tasks benchmarks/agentic/tasks-heavy.jsonl \
        --arms redcon,baseline --phrasing precise --repeats 3 \
        --cache ~/.cache/redcon-agentic-heavy --out-dir benchmarks/agentic/results/agent-heavy
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent  # the redcon checkout that hosts this harness
PILOT_TASKS = _HERE / "pilot-tasks.txt"  # the pinned, reviewable pilot subset

# Three arms. A and Ag both expose the redcon MCP server; Ag adds one neutral
# line of guidance to the prompt. B has no MCP at all. The A-vs-Ag gap isolates
# the cost of the agent not adopting the tools; the Ag-vs-B gap isolates the
# value of the pack once the agent does use it.
GUIDANCE = (
    "This repository has redcon MCP tools available; calling redcon_rank or "
    "redcon_budget first is usually cheaper than searching manually."
)
ARM_SPECS = {
    "redcon": {"mcp": "redcon", "guided": False},  # A
    "redcon_guided": {"mcp": "redcon", "guided": True},  # Ag
    "baseline": {"mcp": "baseline", "guided": False},  # B
    # Agc: redcon plus the shipped installer guidance written to the worktree's
    # AGENTS.md (which the CLI reads automatically), not an inline prompt line.
    # The prompt is identical to baseline; the guidance is delivered exactly as
    # `redcon mcp install` delivers it, so this arm measures the shipped product.
    "redcon_config": {"mcp": "redcon", "guided": False, "install_rules": True},  # Agc
    # P: no MCP. The prompt is prefixed with a redcon pack generated up front, so
    # the agent starts from the map instead of having to call for it. This removes
    # adoption from the equation and measures the pack's pure value against B.
    "preinject": {"mcp": "baseline", "guided": False, "preinject": True},  # P
}
ARMS = ("redcon", "redcon_guided", "baseline")
PREINJECT_BUDGET = 30_000
MODEL = "sonnet"
CANONICAL_MODEL = "claude-sonnet-5"
MAX_TURNS = 30
DEFAULT_TIMEOUT = 1200  # seconds, hard ceiling per run on top of the turn cap


def claude_bin() -> str:
    """The Claude Code executable, from the launcher env or the PATH."""
    return os.environ.get("CLAUDE_CODE_EXECPATH") or "claude"


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return proc.stdout


def write_mcp_configs(out_dir: Path, *, venv_python: str, redcon_root: Path) -> dict[str, Path]:
    """Write the two MCP configs: redcon over stdio, and an empty one.

    The empty config plus --strict-mcp-config guarantees the baseline arm sees
    no MCP server at all, rather than inheriting the user's global config.

    Paths are absolute: the CLI runs with cwd set to the task worktree, so a
    relative config path would resolve against the wrong directory.
    """
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    redcon_cfg = out_dir / "mcp_redcon.json"
    empty_cfg = out_dir / "mcp_empty.json"
    redcon_cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "redcon": {
                        "command": venv_python,
                        "args": ["-m", "redcon", "mcp", "serve"],
                        "env": {"PYTHONPATH": str(redcon_root)},
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    empty_cfg.write_text(json.dumps({"mcpServers": {}}, indent=2), encoding="utf-8")
    return {"redcon": redcon_cfg, "baseline": empty_cfg}


def _task_size(task: dict) -> int:
    """A size proxy: total changed line span across the commit's hunks."""
    span = 0
    for hunks in task.get("hunk_names", {}).values():
        for hunk in hunks:
            start, end = hunk["range"]
            span += max(1, end - start + 1)
    return span


STRATA = ("small", "medium", "large")


def _terciles(tasks: list[dict]) -> dict[str, list[dict]]:
    """Split tasks into small/medium/large thirds by diff size (size then sha)."""
    ranked = sorted(tasks, key=lambda t: (_task_size(t), t["sha"]))
    count = len(ranked)
    first, second = count // 3, 2 * count // 3
    return {"small": ranked[:first], "medium": ranked[first:second], "large": ranked[second:]}


def select_pilot_tasks(tasks: list[dict], *, per_stratum: int = 4) -> list[dict]:
    """Cover the diff-size spectrum: per_stratum tasks from each size tercile,
    spread across repositories so no size band is dominated by one repo.

    This deliberately does not weight toward large commits (which would cherry-
    pick terrain that favours redcon); it samples small, medium and large evenly
    and reports per stratum. Each returned task carries a ``stratum`` label. The
    result is deterministic. With three repos and per_stratum=4, each stratum
    takes one task per repo plus a fourth from a repo that rotates across strata,
    so the three repos end up evenly represented across the twelve.
    """
    strata = _terciles(tasks)
    repos = sorted({t["repo"] for t in tasks})
    picked: list[dict] = []
    seen: set[str] = set()
    for stratum_index, name in enumerate(STRATA):
        by_repo: dict[str, list[dict]] = {}
        for task in sorted(strata[name], key=lambda t: (_task_size(t), t["sha"])):
            by_repo.setdefault(task["repo"], []).append(task)
        chosen: list[dict] = []
        # one near-median task per repo present in this stratum
        for repo in repos:
            group = by_repo.get(repo, [])
            if group:
                chosen.append(group[len(group) // 2])
        # a fourth task from a repo that rotates across strata, next distinct one
        if repos:
            extra_repo = repos[stratum_index % len(repos)]
            chosen_shas = {t["sha"] for t in chosen}
            for task in by_repo.get(extra_repo, []):
                if task["sha"] not in chosen_shas:
                    chosen.append(task)
                    break
        for task in chosen[:per_stratum]:
            if task["sha"] not in seen:
                seen.add(task["sha"])
                picked.append({**task, "stratum": name})
    return picked


def read_task_list(path: Path) -> list[str]:
    """SHAs from a task-list file: first whitespace token per line, '#' comments
    and blank lines ignored. Lets the pilot run a pinned, reviewable subset."""
    shas: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        shas.append(stripped.split()[0])
    return shas


def _select_by_shas(tasks: list[dict], shas: list[str]) -> list[dict]:
    """Tasks whose sha is listed, in the order the list gives them."""
    by_sha = {task["sha"]: task for task in tasks}
    return [by_sha[sha] for sha in shas if sha in by_sha]


def agent_prompt(task: dict, phrasing: str = "precise", *, guided: bool = False) -> str:
    """The instruction handed to the agent. The wording is identical across arms
    except for the optional guidance line (arm Ag), so the tool surface and that
    single line are the only differences between arms."""
    subject = task["phrasings"][phrasing]
    prompt = (
        "You are working inside a git repository checked out at a specific commit. "
        "Implement this change by editing the necessary source files directly:\n\n"
        f"    {subject}\n\n"
        "Make only the edits the change requires. Do not create a git commit and do "
        "not run the test suite. When you are finished, reply with a one-line summary "
        "of what you changed."
    )
    if guided:
        prompt += "\n\n" + GUIDANCE
    return prompt


def _preinject_pack(worktree: Path, task: dict) -> str:
    """A redcon pack for the task at the worktree, rendered as pasteable markdown.

    Generated through the Python API so nothing is written into the worktree (no
    .redcon/ dir that would show up as an edit).
    """
    from redcon.config import default_config  # noqa: PLC0415
    from redcon.core import pipeline  # noqa: PLC0415
    from redcon.core.render import render_pack_markdown  # noqa: PLC0415
    from redcon.stages.workflow import as_json_dict  # noqa: PLC0415

    result = pipeline.run_pack(
        task["phrasings"]["precise"],
        worktree,
        max_tokens=PREINJECT_BUDGET,
        config=default_config(),
        record_history=False,
    )
    return render_pack_markdown(as_json_dict(result))


def build_command(prompt: str, mcp_config: Path) -> list[str]:
    """The full headless CLI command for one run.

    Output is stream-json (with --verbose) so the whole transcript is captured
    and per-run tool usage can be counted; the arm's guidance, if any, is already
    baked into the prompt. The strict MCP config fully controls the tool surface.
    """
    return [
        claude_bin(),
        "-p",
        prompt,
        "--model",
        MODEL,
        "--max-turns",
        str(MAX_TURNS),
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "bypassPermissions",
        "--mcp-config",
        str(mcp_config),
        "--strict-mcp-config",
    ]


def parse_stream(stdout: str) -> tuple[dict, dict[str, int]]:
    """Parse a stream-json transcript into (metrics, tool_call_counts).

    Metrics come from the final ``result`` event; the counts tally every
    ``tool_use`` block across the assistant turns, so ``mcp__redcon__*`` calls
    can be reported as a first-class adoption metric.
    """
    metrics: dict = {}
    counts: dict[str, int] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result":
            usage = event.get("modelUsage", {}).get(CANONICAL_MODEL, {})
            metrics = {
                "is_error": bool(event.get("is_error", False)),
                "terminal_reason": event.get("terminal_reason"),
                "num_turns": event.get("num_turns"),
                "cost_usd": event.get("total_cost_usd"),
                "duration_ms": event.get("duration_ms"),
                "input_tokens": usage.get("inputTokens"),
                "output_tokens": usage.get("outputTokens"),
                "cache_read_tokens": usage.get("cacheReadInputTokens"),
                "cache_creation_tokens": usage.get("cacheCreationInputTokens"),
                "permission_denials": len(event.get("permission_denials", [])),
                "result_summary": (event.get("result") or "")[:280],
            }
        for block in (event.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                counts[block.get("name", "?")] = counts.get(block.get("name", "?"), 0) + 1
    return metrics, counts


def _redcon_calls(counts: dict[str, int]) -> int:
    return sum(v for name, v in counts.items() if str(name).startswith("mcp__redcon__"))


def _files_edited(worktree: Path) -> list[str]:
    """Repo-relative paths the agent created or modified in the worktree."""
    out = _git(worktree, "status", "--porcelain")
    edited = []
    for line in out.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:  # rename: take the destination
            path = path.split(" -> ", 1)[1]
        edited.append(path)
    return sorted(edited)


def _file_hits(changed_files: list[str], edited: list[str]) -> float:
    changed = set(changed_files)
    if not changed:
        return 0.0
    return len(changed & set(edited)) / len(changed)


def run_one(
    task: dict,
    arm: str,
    repeat: int,
    *,
    phrasing: str,
    repo_path: Path,
    worktree: Path,
    mcp_config: Path,
    transcript_dir: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    dry_run: bool = False,
) -> dict:
    """Check out the parent state, run one agent, and return its record.

    ``repeat`` is the repetition index for variance, not an RNG seed. The whole
    stream-json transcript is saved (if ``transcript_dir`` is given) and the
    per-run ``mcp__redcon__*`` call count is recorded.
    """
    spec = ARM_SPECS[arm]
    base = {
        "repo": task["repo"],
        "sha": task["sha"],
        "arm": arm,
        "phrasing": phrasing,
        "repeat": repeat,
        "guided": spec["guided"],
        "stratum": task.get("stratum"),
        "changed_size": _task_size(task),
    }
    prompt = agent_prompt(task, phrasing, guided=spec["guided"])
    command = build_command(prompt, mcp_config)
    if dry_run:
        return {**base, "dry_run": True, "command": command}

    _git(repo_path, "worktree", "add", "--quiet", "--detach", str(worktree), task["parent_sha"])
    if spec.get("install_rules"):
        # Write redcon's shipped instruction block into the client rules files.
        # The installer ships AGENTS.md, but headless Claude Code only reads
        # CLAUDE.md, so the block must land there to reach this agent - place it
        # in both (this is the config-file channel, and a 1.16 install target).
        from redcon.mcp.instructions import (  # noqa: PLC0415
            INSTRUCTIONS_BLOCK,
            ensure_agent_instructions,
        )

        ensure_agent_instructions(worktree)  # AGENTS.md, as shipped today
        (worktree / "CLAUDE.md").write_text(INSTRUCTIONS_BLOCK + "\n", encoding="utf-8")
        base["rules_installed"] = True
    if spec.get("preinject"):
        # Prefix the prompt with a pack generated up front, then rebuild the
        # command. The agent starts from the map instead of calling for one.
        pack_md = _preinject_pack(worktree, task)
        prompt = f"{pack_md}\n\n---\n\nUsing the context above, do the following.\n\n{prompt}"
        command = build_command(prompt, mcp_config)
        base["preinject_chars"] = len(pack_md)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            cwd=str(worktree),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = round(time.monotonic() - started, 3)
        edited = _files_edited(worktree)
        if spec.get("install_rules"):
            # The rules file we wrote is not an agent edit; drop it so it cannot
            # inflate recall or precision.
            edited = [p for p in edited if Path(p).name not in ("AGENTS.md", "CLAUDE.md")]
        if transcript_dir is not None:
            transcript_dir.mkdir(parents=True, exist_ok=True)
            name = f"{task['sha'][:9]}-{arm}-{phrasing}-r{repeat}.jsonl"
            (transcript_dir / name).write_text(proc.stdout, encoding="utf-8")
        metrics, tool_counts = parse_stream(proc.stdout)
        if not metrics:
            return {
                **base,
                "error": "no result event in stream",
                "returncode": proc.returncode,
                "stderr_tail": proc.stderr[-500:],
                "elapsed_wall": elapsed,
            }
        return {
            **base,
            **metrics,
            "model": CANONICAL_MODEL,
            "max_turns": MAX_TURNS,
            "elapsed_wall": elapsed,
            "redcon_tool_calls": _redcon_calls(tool_counts),
            "tool_calls": sum(tool_counts.values()),
            "tool_counts": tool_counts,
            "files_edited": edited,
            "changed_files": list(task["changed_files"]),
            "file_hits": round(_file_hits(task["changed_files"], edited), 6),
        }
    except subprocess.TimeoutExpired:
        return {**base, "error": "timeout", "elapsed_wall": round(time.monotonic() - started, 3)}
    finally:
        with contextlib.suppress(subprocess.CalledProcessError):
            _git(repo_path, "worktree", "remove", "--force", str(worktree))


def run_pilot(
    tasks: list[dict],
    repo_paths: dict[str, Path],
    *,
    arms: tuple[str, ...],
    repeats: int,
    phrasing: str,
    mcp_configs: dict[str, Path],
    worktree_root: Path,
    transcript_dir: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    dry_run: bool = False,
    skip: set[tuple[str, str, str, int]] | None = None,
    max_runs: int = 0,
) -> Iterator[dict]:
    """Yield a record for every task x arm x repeat, one fresh worktree per run.

    Runs in *skip* (already recorded) are not repeated, so an interrupted night
    resumes where it left off. A rate-limited run ends the pass: the pilot backs
    off at the window boundary and picks up in the next window. *max_runs* caps
    the number of live runs this pass (0 = no cap).
    """
    skip = skip or set()
    worktree_root.mkdir(parents=True, exist_ok=True)
    counter = 0
    launched = 0
    for task in tasks:
        repo_path = repo_paths.get(task["repo"])
        if repo_path is None:
            yield {"repo": task["repo"], "sha": task["sha"], "error": "no clone for repo"}
            continue
        for repeat in range(repeats):
            for arm in arms:
                if (task["sha"], arm, phrasing, repeat) in skip:
                    continue
                if max_runs and launched >= max_runs:
                    return
                counter += 1
                worktree = worktree_root / f"wt-{counter}"
                try:
                    record = run_one(
                        task,
                        arm,
                        repeat,
                        phrasing=phrasing,
                        repo_path=repo_path,
                        worktree=worktree,
                        mcp_config=mcp_configs[ARM_SPECS[arm]["mcp"]],
                        transcript_dir=transcript_dir,
                        timeout=timeout,
                        dry_run=dry_run,
                    )
                except Exception as exc:  # noqa: BLE001 - one bad run must not stop the pilot
                    record = {
                        "repo": task["repo"],
                        "sha": task["sha"],
                        "arm": arm,
                        "phrasing": phrasing,
                        "repeat": repeat,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                launched += 1
                yield record
                if not dry_run and _looks_rate_limited(record):
                    yield {"pilot_halt": "rate_limited", "after_runs": launched}
                    return


def _looks_rate_limited(record: dict) -> bool:
    """True if a run stopped because the subscription usage window is exhausted.

    Records that trip this end the current night: the pilot backs off rather
    than burning against a depleted window, and resumes in the next one.
    """
    # result_summary is included so a rate-limit that the CLI reports only in the
    # final text still halts the pass. The trade-off: an agent that itself writes
    # "overloaded" (etc.) in its summary would trip a false halt. Acceptable here
    # because a false halt only pauses the pass, and resume picks it back up.
    haystack = " ".join(
        str(record.get(key, "")).lower()
        for key in ("error", "terminal_reason", "stderr_tail", "result_summary")
    )
    signals = ("rate limit", "rate_limit", "usage limit", "429", "quota", "overloaded")
    return any(signal in haystack for signal in signals)


def completed_keys(out_path: Path) -> set[tuple[str, str, str, int]]:
    """(sha, arm, phrasing, repeat) of runs already recorded, for resume.

    Phrasing is part of the key so a medium-phrasing addendum does not collide
    with the precise runs of the same arm.
    """
    done: set[tuple[str, str, str, int]] = set()
    if not out_path.exists():
        return done
    with out_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if "error" in record or record.get("dry_run"):
                continue
            done.add(
                (
                    record.get("sha"),
                    record.get("arm"),
                    record.get("phrasing", "precise"),
                    int(record.get("repeat", 0)),
                )
            )
    return done


def _append_record(record: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def main() -> int:
    import sys

    sys.path.insert(0, str(_REPO_ROOT))
    from corpus import read_tasks_jsonl  # noqa: PLC0415 - deferred, needs sys.path
    from repos import REPOS  # noqa: PLC0415
    from repos_heavy import REPOS_HEAVY  # noqa: PLC0415
    from runner import ensure_clone  # noqa: PLC0415

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=_HERE / "tasks.jsonl")
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache" / "redcon-agentic")
    parser.add_argument("--out-dir", type=Path, default=_HERE / "results" / "agent")
    parser.add_argument("--worktrees", type=Path, default=Path.home() / ".cache" / "redcon-agent-wt")
    parser.add_argument("--arms", default=",".join(ARMS), help="comma-separated subset of arms")
    parser.add_argument("--repeats", type=int, default=3, help="repetitions per task/arm (variance, not RNG seeds)")
    parser.add_argument("--phrasing", default="precise", choices=("precise", "medium", "vague"))
    parser.add_argument("--limit", type=int, default=0, help="cap number of tasks (0 = all)")
    parser.add_argument(
        "--task-list",
        type=Path,
        default=None,
        help="run only the SHAs listed in this file (one per line, '#' comments ok)",
    )
    parser.add_argument(
        "--pilot",
        action="store_true",
        help=f"run the pinned pilot subset in {PILOT_TASKS.name}",
    )
    parser.add_argument("--max-runs", type=int, default=0, help="cap live runs this pass (0 = all)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--dry-run", action="store_true", help="print commands, run nothing")
    args = parser.parse_args()

    arms = tuple(a.strip() for a in args.arms.split(",") if a.strip())
    all_tasks = read_tasks_jsonl(args.tasks)
    stratum_of = {sha: name for name, group in _terciles(all_tasks).items() for sha in (t["sha"] for t in group)}

    task_list = args.task_list or (PILOT_TASKS if args.pilot else None)
    if task_list:
        tasks = _select_by_shas(all_tasks, read_task_list(task_list))
        print(f"task list {task_list.name}: {len(tasks)} tasks")
    else:
        tasks = all_tasks
    if args.limit:
        tasks = tasks[: args.limit]
    # Keep a task's own stratum if the corpus pinned one (heavy corpus does);
    # otherwise tag from the terciles of the loaded corpus.
    tasks = [{**task, "stratum": task.get("stratum") or stratum_of.get(task["sha"])} for task in tasks]

    specs = {spec.name: spec for spec in (*REPOS, *REPOS_HEAVY)}
    repo_paths: dict[str, Path] = {}
    for name in sorted({task["repo"] for task in tasks}):
        spec = specs.get(name)
        if spec is None:
            continue  # unknown repo yields a per-task error record downstream
        repo_paths[name] = _REPO_ROOT if name == "redcon" else ensure_clone(
            spec.name, spec.url, spec.ref, args.cache
        )

    venv_python = os.environ.get("REDCON_VENV_PYTHON") or sys.executable
    mcp_configs = write_mcp_configs(args.out_dir, venv_python=venv_python, redcon_root=_REPO_ROOT)

    out_path = args.out_dir / "records.jsonl"
    skip = completed_keys(out_path)
    if skip:
        print(f"resuming: {len(skip)} runs already recorded, skipping them")
    total = 0
    for record in run_pilot(
        tasks,
        repo_paths,
        arms=arms,
        repeats=args.repeats,
        phrasing=args.phrasing,
        mcp_configs=mcp_configs,
        worktree_root=args.worktrees,
        transcript_dir=args.out_dir / "transcripts",
        timeout=args.timeout,
        dry_run=args.dry_run,
        skip=skip,
        max_runs=args.max_runs,
    ):
        if record.get("pilot_halt"):
            print(f"pilot halted ({record['pilot_halt']}) after {record['after_runs']} runs this pass")
            _append_record(record, out_path)
            break
        _append_record(record, out_path)
        total += 1
        tag = record.get("arm", "?")
        if record.get("dry_run"):
            print(f"[dry-run] {record['repo']} {record['sha'][:9]} {tag}")
        elif "error" in record:
            print(f"[error] {record['repo']} {record['sha'][:9]} {tag}: {record['error']}")
        else:
            print(
                f"[ok] {record['repo']} {record['sha'][:9]} {tag}/{record.get('phrasing')} "
                f"rep{record['repeat']} turns={record.get('num_turns')} "
                f"cost=${record.get('cost_usd')} redcon_calls={record.get('redcon_tool_calls')} "
                f"file_hits={record.get('file_hits')}"
            )
    print(f"wrote {total} records to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
