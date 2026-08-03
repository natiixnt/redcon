"""Self-contained HTML reports for run, diff and benchmark artifacts.

Each renderer returns one complete HTML document with inline CSS and no
external requests, readable as dark text on a light background when printed.
The content mirrors the Markdown reports and additionally surfaces per-file
``score_breakdown`` and ``role``, the run ``prompt_cache_key``, and the
benchmark ``baseline_comparison``. The JSON and Markdown outputs are untouched;
HTML is an additional, opt-in artifact.
"""

from __future__ import annotations

from html import escape
from typing import Any

_STYLE = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  margin: 0 auto; max-width: 960px; padding: 2rem 1.25rem;
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  color: #14181f; background: #ffffff;
}
h1 { font-size: 1.6rem; margin: 0 0 0.25rem; }
h2 { font-size: 1.15rem; margin: 1.8rem 0 0.6rem; border-bottom: 1px solid #d7dbe0; padding-bottom: 0.2rem; }
.meta { color: #55606d; margin: 0.1rem 0; }
code, .mono { font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace; font-size: 0.88em; }
code { background: #f2f4f7; padding: 0.05rem 0.3rem; border-radius: 3px; }
table { border-collapse: collapse; width: 100%; margin: 0.5rem 0 1rem; }
th, td { border: 1px solid #d7dbe0; padding: 0.35rem 0.55rem; text-align: left; vertical-align: top; }
th { background: #f2f4f7; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
ul { margin: 0.3rem 0 1rem; padding-left: 1.3rem; }
.tag { display: inline-block; background: #e7edf5; color: #24405f; border-radius: 3px; padding: 0 0.35rem; font-size: 0.8em; }
.signals { color: #55606d; font-size: 0.85em; }
.key { background: #f2f4f7; padding: 0.5rem 0.7rem; border-radius: 4px; display: inline-block; }
.empty { color: #55606d; font-style: italic; }
@media print { body { max-width: none; padding: 0; } h2 { break-after: avoid; } table { break-inside: auto; } }
"""


def _esc(value: Any) -> str:
    return escape(str(value), quote=True)


def _doc(title: str, body: str) -> str:
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(title)}</title>\n<style>{_STYLE}</style>\n</head>\n"
        f"<body>\n{body}\n</body>\n</html>\n"
    )


def _table(headers: list[str], rows: list[list[str]], *, numeric: set[int] | None = None) -> str:
    numeric = numeric or set()

    def cell(tag: str, i: int, value: str) -> str:
        cls = ' class="num"' if i in numeric else ""
        return f"<{tag}{cls}>{value}</{tag}>"

    head = "".join(cell("th", i, _esc(h)) for i, h in enumerate(headers))
    body_rows = "".join(
        "<tr>" + "".join(cell("td", i, c) for i, c in enumerate(row)) + "</tr>" for row in rows
    )
    return f"<table>\n<thead><tr>{head}</tr></thead>\n<tbody>{body_rows}</tbody>\n</table>"


def _code(value: Any) -> str:
    return f"<code>{_esc(value)}</code>"


def _file_list(paths: list[str]) -> str:
    if not paths:
        return '<p class="empty">None</p>'
    items = "".join(f"<li>{_code(p)}</li>" for p in paths)
    return f"<ul>{items}</ul>"


def render_run_html(data: dict) -> str:
    """Render a pack run artifact to a self-contained HTML document."""
    budget = data.get("budget", {})
    parts: list[str] = ["<h1>Redcon Pack Report</h1>"]
    parts.append(f'<p class="meta">Task: {_esc(data.get("task", ""))}</p>')
    parts.append(f'<p class="meta">Repository: {_code(data.get("repo", ""))}</p>')
    parts.append(f'<p class="meta">Max tokens: {_esc(data.get("max_tokens", 0))}</p>')

    cache_key = data.get("prompt_cache_key")
    if cache_key:
        parts.append("<h2>Prompt Cache Key</h2>")
        parts.append(f'<p><span class="key mono">{_esc(cache_key)}</span></p>')

    parts.append("<h2>Budget</h2>")
    parts.append(
        _table(
            ["Metric", "Value"],
            [
                ["Estimated input tokens", _esc(budget.get("estimated_input_tokens", 0))],
                ["Estimated saved tokens", _esc(budget.get("estimated_saved_tokens", 0))],
                ["Duplicate reads prevented", _esc(budget.get("duplicate_reads_prevented", 0))],
                ["Quality risk estimate", _esc(budget.get("quality_risk_estimate", "unknown"))],
            ],
            numeric={1},
        )
    )

    parts.append("<h2>Files Included</h2>")
    parts.append(_file_list(data.get("files_included", [])))
    parts.append("<h2>Files Skipped</h2>")
    parts.append(_file_list(data.get("files_skipped", [])))

    parts.append("<h2>Ranked Relevant Files</h2>")
    ranked = data.get("ranked_files", [])
    if ranked:
        rows = []
        for item in ranked:
            role = item.get("role", "")
            role_html = f'<span class="tag">{_esc(role)}</span>' if role else ""
            breakdown = item.get("score_breakdown") or {}
            signals = ", ".join(f"{_esc(k)} {_esc(v)}" for k, v in sorted(breakdown.items()))
            signals_html = f'<div class="signals">{signals}</div>' if signals else ""
            rows.append(
                [
                    _code(item.get("path", ""))
                    + (" " + role_html if role_html else "")
                    + signals_html,
                    _esc(round(float(item.get("score", 0)), 3)),
                ]
            )
        parts.append(_table(["File", "Score"], rows, numeric={1}))
    else:
        parts.append('<p class="empty">No files ranked.</p>')

    return _doc("Redcon Pack Report", "\n".join(parts))


def render_diff_html(data: dict) -> str:
    """Render a diff artifact to a self-contained HTML document."""
    parts: list[str] = ["<h1>Redcon Diff Report</h1>"]
    parts.append(f'<p class="meta">Old run: {_code(data.get("old_run", ""))}</p>')
    parts.append(f'<p class="meta">New run: {_code(data.get("new_run", ""))}</p>')

    task_diff = data.get("task_diff", {})
    parts.append("<h2>Task</h2>")
    parts.append(
        _table(
            ["Field", "Value"],
            [
                ["Old task", _esc(task_diff.get("old_task", ""))],
                ["New task", _esc(task_diff.get("new_task", ""))],
                ["Changed", _esc(task_diff.get("changed", False))],
            ],
        )
    )

    context = data.get("context_diff", {})
    parts.append("<h2>Context</h2>")
    parts.append(f'<p class="meta">Added ({_esc(context.get("added_count", 0))}):</p>')
    parts.append(_file_list(context.get("files_added", [])))
    parts.append(f'<p class="meta">Removed ({_esc(context.get("removed_count", 0))}):</p>')
    parts.append(_file_list(context.get("files_removed", [])))

    changes = data.get("ranked_score_changes", [])
    parts.append("<h2>Ranked Score Changes</h2>")
    if changes:
        rows = [
            [
                _code(c.get("path", "")),
                _esc(c.get("change_type", "")),
                _esc(c.get("old_score")),
                _esc(c.get("new_score")),
                _esc(c.get("delta")),
            ]
            for c in changes
        ]
        parts.append(_table(["File", "Change", "Old", "New", "Delta"], rows, numeric={2, 3, 4}))
    else:
        parts.append('<p class="empty">No score changes.</p>')

    return _doc("Redcon Diff Report", "\n".join(parts))


def render_benchmark_html(data: dict) -> str:
    """Render a benchmark artifact to a self-contained HTML document."""
    parts: list[str] = ["<h1>Redcon Benchmark Report</h1>"]
    parts.append(f'<p class="meta">Task: {_esc(data.get("task", ""))}</p>')
    parts.append(f'<p class="meta">Repository: {_code(data.get("repo", ""))}</p>')
    parts.append(
        f'<p class="meta">Baseline full-context tokens: '
        f"{_esc(data.get('baseline_full_context_tokens', 0))}</p>"
    )
    parts.append(f'<p class="meta">Token budget: {_esc(data.get("max_tokens", 0))}</p>')

    parts.append("<h2>Strategy Comparison</h2>")
    strategies = data.get("strategies", [])
    if strategies:
        rows = [
            [
                _esc(s.get("strategy", "")),
                _esc(s.get("estimated_input_tokens", 0)),
                _esc(s.get("estimated_saved_tokens", 0)),
                _esc(len(s.get("files_included", []))),
                _esc(s.get("quality_risk_estimate", "unknown")),
                _esc(s.get("runtime_ms", 0)),
            ]
            for s in strategies
        ]
        parts.append(
            _table(
                [
                    "Strategy",
                    "Input Tokens",
                    "Saved Tokens",
                    "Files",
                    "Quality Risk",
                    "Runtime (ms)",
                ],
                rows,
                numeric={1, 2, 3, 5},
            )
        )
    else:
        parts.append('<p class="empty">No strategies.</p>')

    comparison = data.get("baseline_comparison")
    if comparison:
        parts.append("<h2>Baseline Comparison</h2>")
        full = comparison.get("baseline_full_context_tokens", {})
        parts.append(
            f'<p class="meta">Baseline task: {_esc(comparison.get("baseline_task", ""))} '
            f"(full-context tokens {_esc(full.get('baseline'))} to {_esc(full.get('current'))})</p>"
        )
        rows = []
        for row in comparison.get("strategies", []):
            rows.append(
                [
                    _esc(row.get("strategy", "")),
                    _esc(row.get("status", "")),
                    _esc(row.get("estimated_input_tokens", {}).get("delta")),
                    _esc(row.get("estimated_saved_tokens", {}).get("delta")),
                    _esc(row.get("runtime_ms", {}).get("delta")),
                ]
            )
        parts.append(
            _table(
                ["Strategy", "Status", "Input Delta", "Saved Delta", "Runtime Delta"],
                rows,
                numeric={2, 3, 4},
            )
        )

    return _doc("Redcon Benchmark Report", "\n".join(parts))
