"""Aggregate per-run results into summary statistics with confidence intervals.

Every mean is reported with a 95% bootstrap confidence interval so that
differences across repos, budgets and phrasings can be read with their
uncertainty. The bootstrap is seeded, so the summary is reproducible.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

_METRICS = ("file_hits", "region_containment", "input_tokens")
_BOOTSTRAP_SAMPLES = 2000
_SEED = 20260806


def load_results(path: Path) -> tuple[list[dict], list[dict]]:
    """Return (valid records, error records) from a results JSONL file."""
    valid: list[dict] = []
    errors: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            (errors if "error" in record else valid).append(record)
    return valid, errors


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def bootstrap_ci(
    values: list[float], *, samples: int = _BOOTSTRAP_SAMPLES, seed: int = _SEED
) -> dict[str, float]:
    """Mean of *values* with a seeded 95% bootstrap confidence interval."""
    if not values:
        return {"mean": 0.0, "low": 0.0, "high": 0.0, "n": 0}
    if len(values) == 1:
        return {"mean": values[0], "low": values[0], "high": values[0], "n": 1}
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(samples):
        resample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(resample) / n)
    means.sort()
    low = means[int(0.025 * samples)]
    high = means[int(0.975 * samples)]
    return {"mean": round(_mean(values), 6), "low": round(low, 6), "high": round(high, 6), "n": n}


def _metric_summary(records: list[dict]) -> dict[str, dict[str, float]]:
    return {
        metric: bootstrap_ci([float(r[metric]) for r in records if metric in r])
        for metric in _METRICS
    }


def _grouped(records: list[dict], key: str) -> dict[str, dict]:
    groups: dict[str, list[dict]] = {}
    for record in records:
        groups.setdefault(str(record.get(key)), []).append(record)
    return {name: _metric_summary(rows) for name, rows in sorted(groups.items())}


def risk_calibration(records: list[dict]) -> dict[str, dict[str, float]]:
    """Mean coverage per reported risk level.

    If risk is calibrated, a higher risk band should coincide with lower file
    and region coverage.
    """
    groups: dict[str, list[dict]] = {}
    for record in records:
        groups.setdefault(str(record.get("risk", "unknown")), []).append(record)
    return {
        risk: {
            "file_hits": round(_mean([float(r["file_hits"]) for r in rows]), 6),
            "region_containment": round(_mean([float(r["region_containment"]) for r in rows]), 6),
            "n": len(rows),
        }
        for risk, rows in sorted(groups.items())
    }


def budget_curve(records: list[dict]) -> list[dict]:
    """Mean coverage at each budget, ascending, for the budget-response curve."""
    groups: dict[int, list[dict]] = {}
    for record in records:
        groups.setdefault(int(record["budget"]), []).append(record)
    curve = []
    for budget in sorted(groups):
        rows = groups[budget]
        curve.append(
            {
                "budget": budget,
                "file_hits": bootstrap_ci([float(r["file_hits"]) for r in rows]),
                "region_containment": bootstrap_ci(
                    [float(r["region_containment"]) for r in rows]
                ),
            }
        )
    return curve


def phrasing_distinguishability(tasks: list[dict]) -> dict:
    """How many tasks have phrasings that actually differ from one another.

    The medium phrasing strips file and symbol names from the precise subject,
    so a subject that carries none of those collapses to medium == precise. The
    by-phrasing means then average over tasks where the phrasings were identical
    by construction, which understates the true sensitivity to wording. Counting
    the distinguishable subset keeps those confidence intervals honest: any
    precise-vs-medium gap can only originate from the tasks reported here.
    """
    total = len(tasks)
    medium_differs = 0
    all_three_distinct = 0
    by_repo: dict[str, dict[str, int]] = {}
    for task in tasks:
        phrasings = task.get("phrasings", {})
        precise = phrasings.get("precise")
        medium = phrasings.get("medium")
        vague = phrasings.get("vague")
        differs = medium is not None and medium != precise
        distinct = differs and vague not in (precise, medium)
        medium_differs += int(differs)
        all_three_distinct += int(distinct)
        bucket = by_repo.setdefault(str(task.get("repo", "?")), {"total": 0, "medium_differs": 0})
        bucket["total"] += 1
        bucket["medium_differs"] += int(differs)
    return {
        "total": total,
        "medium_differs_precise": medium_differs,
        "all_three_distinct": all_three_distinct,
        "by_repo": dict(sorted(by_repo.items())),
    }


def summarize(records: list[dict], *, tasks: list[dict] | None = None) -> dict:
    """Full aggregate: overall, per-repo/budget/phrasing, risk calibration, curve.

    When *tasks* (the corpus) is supplied, a phrasing-distinguishability block is
    added so the by-phrasing means can be read against how many tasks actually
    had distinct wordings.
    """
    summary = {
        "runs": len(records),
        "overall": _metric_summary(records),
        "by_repo": _grouped(records, "repo"),
        "by_budget": _grouped(records, "budget"),
        "by_phrasing": _grouped(records, "phrasing"),
        "risk_calibration": risk_calibration(records),
        "budget_curve": budget_curve(records),
    }
    if tasks is not None:
        summary["phrasing_distinguishability"] = phrasing_distinguishability(tasks)
    return summary
