"""Render an aggregate summary into a Markdown report."""

from __future__ import annotations


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _ci(stat: dict[str, float], *, as_pct: bool = True) -> str:
    fmt = _pct if as_pct else (lambda v: f"{v:,.0f}")
    return f"{fmt(stat['mean'])} [{fmt(stat['low'])}, {fmt(stat['high'])}]"


def _metric_table(title: str, groups: dict[str, dict]) -> list[str]:
    lines = [f"### {title}", ""]
    lines.append("| Group | File hits (95% CI) | Region containment (95% CI) | Input tokens (95% CI) | n |")
    lines.append("|---|---|---|---|---|")
    for name, stats in groups.items():
        lines.append(
            f"| {name} | {_ci(stats['file_hits'])} | {_ci(stats['region_containment'])} "
            f"| {_ci(stats['input_tokens'], as_pct=False)} | {stats['file_hits']['n']} |"
        )
    lines.append("")
    return lines


def render(summary: dict, *, errors: int = 0) -> str:
    lines: list[str] = [
        "# Agentic Context Evaluation",
        "",
        f"Deterministic runs: {summary['runs']} (errors: {errors}).",
        "",
        "Each task is a real commit evaluated at its parent state. File hits is the",
        "recall of the changed files among the packed files; region containment is",
        "the fraction of changed line ranges the packed selection surfaces verbatim.",
        "Means carry a seeded 95% bootstrap confidence interval.",
        "",
        "## Overall",
        "",
        f"- File hits: {_ci(summary['overall']['file_hits'])}",
        f"- Region containment: {_ci(summary['overall']['region_containment'])}",
        f"- Input tokens: {_ci(summary['overall']['input_tokens'], as_pct=False)}",
        "",
        "## Breakdowns",
        "",
    ]
    lines += _metric_table("By repository", summary["by_repo"])
    lines += _metric_table("By budget", summary["by_budget"])
    lines += _metric_table("By phrasing", summary["by_phrasing"])

    lines += ["## Risk calibration", ""]
    lines.append("A calibrated risk should show lower coverage at higher risk.")
    lines.append("")
    lines.append("| Risk | File hits | Region containment | n |")
    lines.append("|---|---|---|---|")
    for risk, stats in summary["risk_calibration"].items():
        lines.append(
            f"| {risk} | {_pct(stats['file_hits'])} | {_pct(stats['region_containment'])} "
            f"| {stats['n']} |"
        )
    lines.append("")

    lines += ["## Budget curve", ""]
    lines.append("| Budget | File hits (95% CI) | Region containment (95% CI) |")
    lines.append("|---|---|---|")
    for point in summary["budget_curve"]:
        lines.append(
            f"| {point['budget']:,} | {_ci(point['file_hits'])} "
            f"| {_ci(point['region_containment'])} |"
        )
    lines.append("")
    return "\n".join(lines)
