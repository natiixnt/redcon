# Agentic context evaluation harness

A deterministic, research-grade evaluation of redcon's context selection against
real code changes. Every task is a real commit: redcon sees the repository at the
commit's parent state, and the files and line ranges the commit changed are the
ground truth it should surface. Nothing about the change itself can leak into the
selection.

## What it measures

For each task x budget x phrasing, the runner records:

- **file_hits** - recall of the changed files among the packed files.
- **region_containment** - fraction of the changed line ranges whose lines the
  packed selection surfaces verbatim (a summary that names but does not include
  the lines does not count).
- **input_tokens**, **baseline_tokens**, **risk**, **cache_key**, **elapsed**.

Three phrasings of each task probe robustness to how a request is worded:

- **precise** - the commit subject.
- **medium** - the subject with file and symbol names stripped out.
- **vague** - a template naming only the area of the tree that changed.

## Pinned corpus

`tasks.jsonl` is pinned in the repo (210 tasks: 70 each from redcon at
`v1.15.0`, and the permissive Python projects httpx and click at fixed SHAs; see
`repos.py`). The external repos are cloned into a cache by the runner, never
vendored. At three budgets (12k / 30k / 60k) and three phrasings that is 1,890
deterministic runs.

## Modules

- `corpus.py` - build tasks from git history (filters: no-merge, task-like
  subject, changes >= 1 existing source file, source diff under 400 lines).
- `runner.py` - worktree at parent state, run `redcon pack` with default config,
  compute per-run metrics.
- `metrics.py` - aggregation with a seeded 95% bootstrap CI, breakdowns by
  repo/budget/phrasing, risk calibration, and a budget-response curve.
- `report.py` - render the summary to Markdown.
- `build_corpus.py` / `run.py` - regenerate the corpus and run the evaluation.

## Reproduce

```bash
# Regenerate the pinned corpus (clones httpx and click into the cache):
python benchmarks/agentic/build_corpus.py --cache ~/.cache/redcon-agentic

# Run the full layer-1 evaluation (redcon only, no LLM, no API cost):
python benchmarks/agentic/run.py --cache ~/.cache/redcon-agentic --out-dir benchmarks/agentic/results
```

The harness itself is covered by `tests/test_agentic_harness.py`, which runs on a
synthetic five-commit fixture in the normal test suite.

This is layer 1: redcon-only and deterministic. A layer-2 agent-in-the-loop arm
(comparing an agent with and without redcon) is gated separately because it
requires an LLM API key and incurs cost.
