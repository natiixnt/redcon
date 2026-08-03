"""Benchmark baseline comparison and CSV export.

`redcon benchmark --baseline prior.json` adds a deterministic per-strategy
delta against an earlier benchmark, and `--csv` writes a per-strategy CSV
alongside the JSON/Markdown. Defaults (no flags) are unchanged.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from redcon.cli import build_parser
from redcon.core.benchmark import benchmark_csv_rows, compare_benchmarks
from redcon.core.render import render_benchmark_comparison_markdown


def _bench(strategies: list[dict], full_tokens: int = 1000) -> dict:
    return {
        "command": "benchmark",
        "task": "demo",
        "repo": ".",
        "max_tokens": 5000,
        "baseline_full_context_tokens": full_tokens,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "strategies": strategies,
    }


def _strategy(name: str, inp: int, saved: int, runtime: int, files: int = 2) -> dict:
    return {
        "strategy": name,
        "estimated_input_tokens": inp,
        "estimated_saved_tokens": saved,
        "runtime_ms": runtime,
        "files_included": [f"f{i}.py" for i in range(files)],
        "files_skipped": [],
        "duplicate_reads_prevented": 0,
        "cache_hits": 0,
        "quality_risk_estimate": "low",
    }


def test_compare_benchmarks_computes_deltas() -> None:
    baseline = _bench([_strategy("compressed_pack", 400, 600, 30)], full_tokens=1000)
    current = _bench([_strategy("compressed_pack", 300, 700, 25)], full_tokens=900)
    comp = compare_benchmarks(baseline, current)

    assert comp["baseline_full_context_tokens"]["delta"] == -100
    row = comp["strategies"][0]
    assert row["status"] == "compared"
    assert row["estimated_input_tokens"] == {"baseline": 400, "current": 300, "delta": -100}
    assert row["estimated_saved_tokens"]["delta"] == 100
    assert row["runtime_ms"]["delta"] == -5


def test_compare_flags_added_and_removed_strategies() -> None:
    baseline = _bench([_strategy("only_old", 100, 0, 10)])
    current = _bench([_strategy("only_new", 200, 0, 20)])
    comp = compare_benchmarks(baseline, current)
    by_name = {r["strategy"]: r for r in comp["strategies"]}
    assert by_name["only_old"]["status"] == "removed"
    assert by_name["only_new"]["status"] == "added"
    # A strategy in only one run has no numeric delta.
    assert by_name["only_new"]["estimated_input_tokens"]["delta"] is None


def test_compare_is_deterministic() -> None:
    baseline = _bench([_strategy("b", 400, 600, 30), _strategy("a", 100, 200, 10)])
    current = _bench([_strategy("a", 90, 210, 9), _strategy("b", 380, 620, 28)])
    first = compare_benchmarks(baseline, current)
    second = compare_benchmarks(baseline, current)
    assert first == second
    # Strategies are emitted in a stable sorted order regardless of input order.
    assert [r["strategy"] for r in first["strategies"]] == ["a", "b"]


def test_csv_rows_without_comparison() -> None:
    data = _bench([_strategy("compressed_pack", 300, 700, 25, files=3)])
    header, rows = benchmark_csv_rows(data)
    assert header[0] == "strategy"
    assert "baseline_estimated_input_tokens" not in header
    assert rows[0][0] == "compressed_pack"
    assert rows[0][header.index("estimated_input_tokens")] == 300
    assert rows[0][header.index("files_included")] == 3


def test_csv_rows_with_comparison_add_delta_columns() -> None:
    baseline = _bench([_strategy("compressed_pack", 400, 600, 30)])
    current = _bench([_strategy("compressed_pack", 300, 700, 25)])
    comp = compare_benchmarks(baseline, current)
    header, rows = benchmark_csv_rows(current, comp)
    assert "estimated_input_tokens_delta" in header
    assert rows[0][header.index("baseline_estimated_input_tokens")] == 400
    assert rows[0][header.index("estimated_input_tokens_delta")] == -100
    assert rows[0][header.index("estimated_saved_tokens_delta")] == 100


def test_comparison_markdown_has_section_and_signed_deltas() -> None:
    baseline = _bench([_strategy("compressed_pack", 400, 600, 30)])
    current = _bench([_strategy("compressed_pack", 300, 700, 25)])
    md = render_benchmark_comparison_markdown(compare_benchmarks(baseline, current))
    assert "## Baseline Comparison" in md
    assert "+100" in md  # saved-tokens delta rendered with sign
    assert "-100" in md  # input-tokens delta


def _run_benchmark(tmp_path: Path, out_prefix: Path, extra: list[str]) -> int:
    (tmp_path / "auth.py").write_text("def login(token):\n    return bool(token)\n")
    parser = build_parser()
    args = parser.parse_args(
        ["benchmark", "make auth safer", "--repo", str(tmp_path), "--out-prefix", str(out_prefix)]
        + extra
    )
    return int(args.func(args))


def test_cli_benchmark_baseline_and_csv_end_to_end(tmp_path: Path) -> None:
    first = tmp_path / "first"
    assert _run_benchmark(tmp_path, first, []) == 0
    assert not first.with_suffix(".csv").exists()  # csv is opt-in

    second = tmp_path / "second"
    rc = _run_benchmark(tmp_path, second, ["--baseline", str(first) + ".json", "--csv"])
    assert rc == 0

    result = json.loads((second.with_suffix(".json")).read_text())
    assert "baseline_comparison" in result

    with (second.with_suffix(".csv")).open() as fh:
        table = list(csv.reader(fh))
    assert table[0][0] == "strategy"
    assert "estimated_input_tokens_delta" in table[0]
    assert len(table) > 1


def test_cli_benchmark_rejects_non_benchmark_baseline(tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.json"
    bogus.write_text(json.dumps({"command": "pack"}))
    rc = _run_benchmark(tmp_path, tmp_path / "out", ["--baseline", str(bogus)])
    assert rc == 1
