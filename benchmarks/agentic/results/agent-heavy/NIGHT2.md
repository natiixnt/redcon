# Agent arm, night 2: context-heavy corpus (pre-registration)

This file is committed before the run: the hypotheses below are registered up
front, and the results are filled in afterwards under each one.

Night 1 found no end-task benefit from redcon on small repositories and traced
the one clear loss to a behavioural cause - the agent never called redcon's
tools and grepped by hand instead. Night 2 separates the two questions night 1
conflated: does the pack help when it is used, and how often does the agent use
it unprompted.

## Design

- Corpus: `benchmarks/agentic/tasks-heavy.jsonl` - 12 tasks from django and
  sympy (large repos, several million tokens each), touching 3-8 files across
  >= 2 directories, 60-400 line diffs, stratified 4 small / 4 medium / 4 large.
- Three arms:
  - **A** (`redcon`): redcon MCP available, prompt identical to baseline.
  - **Ag** (`redcon_guided`): redcon MCP available, prompt plus one neutral line
    ("This repository has redcon MCP tools available; calling redcon_rank or
    redcon_budget first is usually cheaper than searching manually.").
  - **B** (`baseline`): no MCP at all.
- Decomposition: **pack value = Ag vs B**; **cost of non-adoption = A vs Ag**.
- Model sonnet, `--max-turns 30`, window-aware and resumable. Every run is
  captured as a stream-json transcript (kept under `transcripts/`), and the
  per-run count of `mcp__redcon__*` calls is recorded as a first-class metric -
  without it adoption and value cannot be told apart.
- Passes: pass 1 = 12 x {A, B} x 3 (precise); pass 2 = 12 x Ag x 3 (precise) plus
  a medium addendum 12 x {Ag, B} x 1.

## Pre-registered hypotheses

1. **Pack value.** On these large repos, Ag beats B on cost at equal or better
   recall.
2. **Cost of non-adoption.** A minus Ag is non-trivial and is explained by redcon
   tool-call counts (A calls the tools rarely, Ag often). This is a
   tool-description problem, not a pack-value problem.
3. **Wording sensitivity.** Ag's advantage over B grows from precise to medium.

## Caveat, registered up front

Medium differs from precise for only 8 of the 12 tasks - 4 sympy subjects name no
file or symbol, so their medium collapses onto precise. The precise-vs-medium
comparison (hypothesis 3) is therefore reported on that distinguishable subset,
with the count stated, so the medium addendum is not read as more than it is.

## Results

<!-- Filled in after the passes complete. -->
