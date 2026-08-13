"""Experiment 6 Phase A: offline ceiling for tool-result compression.

No agent spend, no product change. Re-renders the tool RESULTS in the night-2
stream-json transcripts through redcon's existing machinery (file reads through
the adaptive whole/symbol logic, shell output through the command compressors),
counts tokens original vs compressed with the standard estimator, and reports the
savings and two safety signals from data we already have:

- edit-line coverage: for each file the agent later edited, whether the compressed
  rendering of its earlier read still contained the eventually-edited lines;
- re-read exposure: how often the agent read the same file more than once.

    python benchmarks/agentic/exp6_toolresult_analysis.py \\
        --transcripts /tmp/night2-transcripts --out results/exp6-phaseA

Tool-result compression is the third delivery channel: unlike pull (the model must
opt in) and push (unrequested context injected up front), it only shrinks what the
agent already asked for, so cost strictly drops; the open question is quality.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from redcon.cmd.budget import BudgetHint  # noqa: E402
from redcon.cmd.compressors.base import CompressorContext  # noqa: E402
from redcon.cmd.registry import detect_compressor  # noqa: E402
from redcon.compressors.symbols import select_symbol_aware_chunks  # noqa: E402
from redcon.core.text import task_keywords  # noqa: E402
from redcon.core.tokens import estimate_tokens  # noqa: E402

# Adaptive threshold: a read at or below this many tokens is delivered whole (no
# compression); larger reads are symbol-compressed. Matches the pack default
# full_file_threshold_tokens.
WHOLE_THRESHOLD_TOKENS = 300
# Line budget for per-read symbol extraction (between the snippet fallback and the
# total line limit defaults). Stated so the ceiling is reproducible.
READ_LINE_BUDGET = 80
# Transcript filenames abbreviate the task sha to this many hex chars.
_SHA_PREFIX_LEN = 9

_ARM_RE = re.compile(r"^([0-9a-f]+)-([a-z0-9_]+)-(precise|medium|vague)-r(\d+)$")
_LINE_PREFIX = re.compile(r"^\s*\d+\t")


def _parse_name(path: Path) -> dict | None:
    m = _ARM_RE.match(path.stem)
    if not m:
        return None
    return {"sha": m.group(1), "arm": m.group(2), "phrasing": m.group(3), "repeat": int(m.group(4))}


def _strip_line_numbers(text: str) -> str:
    """Turn Read output (``   123\\t<line>``) back into raw file text."""
    out = []
    for line in text.splitlines():
        out.append(_LINE_PREFIX.sub("", line, count=1))
    return "\n".join(out)


def _iter_tool_pairs(path: Path):
    """Yield (name, input, result_text) in order, matched by tool_use_id."""
    uses: dict[str, dict] = {}
    order: list[str] = []
    results: dict[str, str] = {}
    for line in path.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = event.get("message") or {}
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                uses[block.get("id")] = {
                    "name": block.get("name"),
                    "input": block.get("input") or {},
                }
                order.append(block.get("id"))
            elif block.get("type") == "tool_result":
                raw = block.get("content")
                if isinstance(raw, list):
                    raw = " ".join(x.get("text", "") for x in raw if isinstance(x, dict))
                results[block.get("tool_use_id")] = raw or ""
    for tid in order:
        use = uses[tid]
        yield use["name"], use["input"], results.get(tid, "")


def _first_segment_argv(command: str) -> tuple[str, ...]:
    """argv of the first pipeline/compound segment, for compressor detection."""
    head = re.split(r"[|;]| && | \|\| ", command.strip(), maxsplit=1)[0]
    try:
        return tuple(shlex.split(head))
    except ValueError:
        return tuple(head.split())


def _classify(name: str, cmd_input: dict) -> str:
    if name == "Read":
        return "read"
    if name in ("Grep", "Glob"):
        return "grep"
    if name != "Bash":
        return "other"
    argv = _first_segment_argv(str(cmd_input.get("command", "")))
    head = Path(argv[0]).name if argv else ""
    if head in ("grep", "rg", "egrep", "fgrep", "ag", "ack"):
        return "grep"
    if head in ("pytest", "py.test"):
        return "pytest"
    if head == "git" and len(argv) > 1:
        return f"git_{argv[1]}"
    if head in ("ls", "find", "tree"):
        return "listing"
    return "bash_other"


def _compress_read(cmd_input: dict, result_text: str, keywords: list[str]) -> tuple[int, int, str]:
    """Return (original_tokens, compressed_tokens, delivery) for a Read result."""
    raw = _strip_line_numbers(result_text)
    original = estimate_tokens(raw)
    if original <= WHOLE_THRESHOLD_TOKENS:
        return original, original, "whole"
    file_path = str(cmd_input.get("file_path", "read.txt"))
    extraction = select_symbol_aware_chunks(
        file_path=file_path, text=raw, keywords=keywords, line_budget=READ_LINE_BUDGET
    )
    if extraction is None or not getattr(extraction, "text", ""):
        return original, original, "whole"  # nothing to extract: keep whole
    compressed = min(estimate_tokens(extraction.text), original)
    return original, compressed, "compressed"


def _compress_shell(name: str, cmd_input: dict, result_text: str) -> tuple[int, int]:
    """Return (original_tokens, compressed_tokens) for a shell/grep result."""
    original = estimate_tokens(result_text)
    argv = (
        _first_segment_argv(str(cmd_input.get("command", "")))
        if name == "Bash"
        else (name.lower(),)
    )
    compressor = detect_compressor(argv) if argv else None
    if compressor is None:
        return original, original
    # A realistic hint: large outputs are compacted, small ones stay verbose. Stated
    # so the ceiling is reproducible; quality_floor defaults to the library's choice.
    hint = BudgetHint(remaining_tokens=8000, max_output_tokens=4000)
    ctx = CompressorContext(argv=argv, cwd="", returncode=0, hint=hint)
    try:
        out = compressor.compress(result_text.encode("utf-8"), b"", ctx)
    except Exception:  # noqa: BLE001 - a parser failure just means no compression
        return original, original
    return out.original_tokens or original, min(out.compressed_tokens, original)


def _edited_line_ranges(
    cmd_input: dict, read_bodies: dict[str, str]
) -> tuple[str, set[int]] | None:
    """For an Edit, locate the edited region in the file's most recent read body and
    return (path, set of 1-based line numbers) it touched. None if not locatable."""
    path = str(cmd_input.get("file_path", ""))
    old = cmd_input.get("old_string")
    body = read_bodies.get(path)
    if not path or not old or not body:
        return None
    idx = body.find(old)
    if idx < 0:
        return None
    start_line = body.count("\n", 0, idx) + 1
    end_line = start_line + old.count("\n")
    return path, set(range(start_line, end_line + 1))


def analyse(transcripts: Path, tasks: dict[str, dict]) -> dict:
    rows: list[dict] = []  # per tool-result
    edit_cov: list[dict] = []  # per edited file
    reread = []  # per run: max reads of one file
    for path in sorted(transcripts.rglob("*.jsonl")):
        meta = _parse_name(path)
        if not meta:
            continue
        keywords = task_keywords(tasks.get(meta["sha"], {}).get("phrasings", {}).get("precise", ""))
        read_bodies: dict[str, str] = {}  # path -> raw body of most recent read (line-stripped)
        read_delivery: dict[str, str] = {}  # path -> whole/compressed of most recent read
        read_counts: Counter = Counter()
        for name, cmd_input, result_text in _iter_tool_pairs(path):
            if not result_text:
                continue
            kind = _classify(name, cmd_input)
            if kind == "read":
                orig, comp, delivery = _compress_read(cmd_input, result_text, keywords)
                fp = str(cmd_input.get("file_path", ""))
                if fp:
                    read_bodies[fp] = _strip_line_numbers(result_text)
                    read_delivery[fp] = delivery
                    read_counts[fp] += 1
            elif kind in ("grep", "pytest", "listing", "bash_other") or kind.startswith("git_"):
                orig, comp = _compress_shell(name, cmd_input, result_text)
                delivery = ""
            else:
                orig = comp = estimate_tokens(result_text)
                delivery = ""
            rows.append({**meta, "kind": kind, "original": orig, "compressed": comp})

            if name == "Edit":
                located = _edited_line_ranges(cmd_input, read_bodies)
                if located:
                    fp, lines = located
                    delivery = read_delivery.get(fp, "whole")
                    if delivery == "whole":
                        covered = True  # whole read keeps every line
                    else:
                        # Re-render compressed and check the edited lines survive by content.
                        covered = _lines_survive(fp, read_bodies[fp], lines, keywords)
                    edit_cov.append({**meta, "path": fp, "delivery": delivery, "covered": covered})
        if read_counts:
            reread.append(
                {
                    **meta,
                    "max_reads": max(read_counts.values()),
                    "rereads": sum(c for c in read_counts.values() if c > 1)
                    - sum(1 for c in read_counts.values() if c > 1),
                }
            )
    return {"rows": rows, "edit_cov": edit_cov, "reread": reread}


def _lines_survive(file_path: str, body: str, edited_lines: set[int], keywords: list[str]) -> bool:
    """Whether the symbol-compressed rendering of *body* still contains the text of
    the edited lines (content match, whitespace-tolerant)."""
    extraction = select_symbol_aware_chunks(
        file_path=file_path, text=body, keywords=keywords, line_budget=READ_LINE_BUDGET
    )
    if extraction is None or not getattr(extraction, "text", ""):
        return True
    compressed_lines = {ln.strip() for ln in extraction.text.splitlines() if ln.strip()}
    body_lines = body.splitlines()
    for n in edited_lines:
        if 1 <= n <= len(body_lines):
            target = body_lines[n - 1].strip()
            if target and target not in compressed_lines:
                return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcripts", type=Path, default=Path("/tmp/night2-transcripts"))
    parser.add_argument("--tasks", type=Path, default=_HERE / "tasks-heavy.jsonl")
    parser.add_argument("--out", type=Path, default=_HERE / "results" / "exp6-phaseA")
    args = parser.parse_args()

    # Transcript filenames carry a short sha prefix; tasks store the full 40-char
    # sha. Key tasks by the same prefix length so keyword lookup actually hits.
    tasks = {}
    for line in args.tasks.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        tasks[record["sha"][:_SHA_PREFIX_LEN]] = record
    result = analyse(args.transcripts, tasks)
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "toolresult_rows.jsonl").open("w", encoding="utf-8") as handle:
        for row in result["rows"]:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    with (args.out / "edit_coverage.jsonl").open("w", encoding="utf-8") as handle:
        for row in result["edit_cov"]:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    _report(result)
    return 0


def _pct(n: int, d: int) -> float:
    return 100.0 * n / d if d else 0.0


def _report(result: dict) -> None:
    rows = result["rows"]
    print("\n=== Exp 6 Phase A: tool-result compression ceiling (night-2, offline) ===")
    print(
        f"tool-results analysed: {len(rows)} across {len({(r['sha'], r['arm'], r['repeat']) for r in rows})} runs"
    )

    # Savings by tool type (primary: baseline arm).
    def savings_table(subset, label):
        by_kind = defaultdict(list)
        for r in subset:
            by_kind[r["kind"]].append(r)
        print(f"\n[{label}] savings by tool type")
        header = ("kind", "n", "orig_tok", "comp_tok", "save%", "med%")
        print(
            f"{header[0]:<12} {header[1]:>5} {header[2]:>10} {header[3]:>10} {header[4]:>7} {header[5]:>7}"
        )
        tot_o = tot_c = 0
        for kind in sorted(by_kind, key=lambda k: -sum(x["original"] for x in by_kind[k])):
            g = by_kind[kind]
            o = sum(x["original"] for x in g)
            c = sum(x["compressed"] for x in g)
            tot_o += o
            tot_c += c
            per = [100.0 * (1 - x["compressed"] / x["original"]) for x in g if x["original"] > 0]
            med = st.median(per) if per else 0.0
            print(f"{kind:<12} {len(g):>5} {o:>10} {c:>10} {_pct(o - c, o):>6.1f}% {med:>6.1f}%")
        print(
            f"{'TOTAL':<12} {len(subset):>5} {tot_o:>10} {tot_c:>10} {_pct(tot_o - tot_c, tot_o):>6.1f}%"
        )

    baseline = [r for r in rows if r["arm"] == "baseline"]
    savings_table(baseline, "baseline arm (primary)")
    savings_table(rows, "all arms")

    # Per-run share of input.
    per_run = defaultdict(lambda: [0, 0])
    for r in baseline:
        key = (r["sha"], r["repeat"])
        per_run[key][0] += r["original"]
        per_run[key][1] += r["compressed"]
    shares = [100.0 * (1 - c / o) for o, c in per_run.values() if o > 0]
    if shares:
        print(
            f"\n[baseline] per-run tool-result token reduction: median {st.median(shares):.1f}%, "
            f"p25 {_quantile(shares, 0.25):.1f}%, p75 {_quantile(shares, 0.75):.1f}%"
        )

    # Safety: edit-line coverage.
    ec = result["edit_cov"]
    if ec:
        overall = _pct(sum(1 for e in ec if e["covered"]), len(ec))
        whole = [e for e in ec if e["delivery"] == "whole"]
        comp = [e for e in ec if e["delivery"] == "compressed"]
        print(f"\n[safety] edit-line coverage over {len(ec)} edited-file reads: {overall:.1f}%")
        print(
            f"  when read delivered whole ({len(whole)}): {_pct(sum(e['covered'] for e in whole), len(whole)):.1f}%"
        )
        print(
            f"  when read delivered compressed ({len(comp)}): {_pct(sum(e['covered'] for e in comp), len(comp)):.1f}%"
        )

    # Re-read exposure.
    rr = result["reread"]
    if rr:
        multi = sum(1 for r in rr if r["max_reads"] > 1)
        print(
            f"\n[re-read] runs with any file read more than once: {multi}/{len(rr)} "
            f"({_pct(multi, len(rr)):.1f}%); mean max-reads-of-one-file "
            f"{st.mean(r['max_reads'] for r in rr):.2f}"
        )


def _quantile(values: list[float], q: float) -> float:
    s = sorted(values)
    if not s:
        return 0.0
    idx = min(len(s) - 1, int(q * (len(s) - 1)))
    return s[idx]


if __name__ == "__main__":
    raise SystemExit(main())
