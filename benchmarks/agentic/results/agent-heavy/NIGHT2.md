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

## Pass 1 results (arms A and B, precise, 72 runs, one window)

Zero adoption. Arm A called a redcon tool 0 times across all 36 runs, on repos of
several million tokens. "Available but unprompted" is pure schema overhead with no
use, and A comes out slightly behind B.

| arm | cost/run | turns | recall | precision | capped | redcon calls |
|---|---|---|---|---|---|---|
| A (redcon) | $0.82 | 23.2 | 0.62 | 0.82 | 16/36 | 0 |
| B (baseline) | $0.78 | 19.8 | 0.69 | 0.80 | 10/36 | 0 |

The night-1 audit (the agent greps by hand instead of ranking) is confirmed at
full scale. This makes pass 2 the decisive test: whether one guidance line moves
adoption off zero, and if so whether the pack then pays.

## Pre-registered interpretation of pass 2 (recorded before pass 2 ran)

Fixed in advance so no narrative is fitted after the fact:

- **Ag adopts and beats B** (cost down at equal-or-better recall): thesis
  conditionally confirmed - the pack works when the agent uses it. Action for
  1.16: ship guidance by default (installer writes a client rule) and slim the
  tool schemas.
- **Ag adopts but does not beat B**: pack value on this terrain is refuted. Then a
  serious repositioning conversation - token savings in API/CI workflows and cache
  stability, not "better interactive-agent outcomes".
- **Ag does not adopt**: one prompt line is not enough; the next measured step is a
  client config-file rule (CLAUDE.md-style), which is exactly what the installer
  can write.
- **Mixed by stratum**: an applicability-boundary map for the writeup.

Independent of the outcome, one finding is already hard and goes to 1.16: adoption
is a first-class product problem. A tool the agent does not call does not exist,
however good the pack.

## Causal-chain protocol for the Ag transcripts

Adoption plus a win is only a correlation; the transcripts turn it into a chain.
For every Ag run, read from the stream-json transcript and report per run: which
redcon tools were called and at which turn, the file set redcon_rank/redcon_budget
returned, and the overlap of files_edited with that set - i.e. did the agent edit
the files the pack pointed at, and did cost fall as a result.

## Pass 2 results

<!-- Filled in after pass 2 completes. -->
