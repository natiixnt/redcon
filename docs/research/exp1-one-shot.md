# Experiment 1 design: one-shot selection quality

Status: **design only, pre-registered. No runs until this design is approved and
Natalia confirms a usage window.**

## Motivation

Night 2 showed that in a multi-turn agent loop redcon delivers no end-task
benefit on large repos: adoption is near-zero (pull), and pre-injecting the full
map hurts (push, even at 0.90 coverage). But every one of those runs conflates
two things: the *quality of redcon's selection* and the *agent's behaviour in a
loop*. This experiment isolates selection quality by removing the loop entirely.

## Design

A single model call per task. The context is composed up front and the model
answers once; there is no tool loop, so adoption and turn dynamics cannot
confound the result. Arms, all given the **same token budget**:

- **redcon** - the redcon pack for the task (budget from the 1.16 size-scaled
  default).
- **naive** - a simple baseline retrieval: keyword/grep the task terms, take the
  top-N files by match count, and include them to the same budget.
- **repo-map** (optional) - an aider-style repository map to the same budget, only
  if it is cheap to reproduce faithfully.

Because the budget is equal by construction, **cost is identical across arms**;
the only thing that varies is what got selected.

### Naive baseline, pinned (deterministic)

So the baseline is not a moving target:

- **Keywords:** from the precise phrasing only. Lowercase, split on non-
  alphanumeric characters, drop tokens shorter than 3 characters and a fixed
  English stopword list. This set is the query.
- **Scoring:** per candidate source file, the total count of keyword occurrences
  in its content (match count).
- **Tie-breaks (fully deterministic):** higher match count first; ties broken by
  shorter path, then lexicographic path.
- **Truncation to budget:** walk files in ranked order and include each file whole
  until the next file would exceed the token budget; a file that does not fit is
  dropped entirely (no partial files). The budget is the same size-scaled value
  redcon's pack uses for the task, so both arms carry the same token count.

### Response format, forced identically

Every arm is instructed to output **only a unified diff** (git-style patch) and
nothing else, so the parser and the metric are identical across arms and the
format cannot advantage one arm.

- **Corpora:** `tasks-heavy.jsonl` (django, sympy) plus 12 tasks from the small
  corpus for contrast.
- **Model:** sonnet, single call, deterministic prompt; a few repeats for
  variance.

### Diff-overlap metric, defined before the run

Let `GT` be the real commit's changed files and, per file, its parent-side changed
line ranges; let `P` be the model's unified-diff patch.

- **File-level overlap** = `|files(P) intersect GT_files| / |GT_files|` - the
  fraction of ground-truth files the patch touches.
- **Line-level overlap** = across `GT` files, `|changed_lines(P) intersect
  GT_lines| / |GT_lines|`, where a line matches after stripping leading and
  trailing whitespace (whitespace-tolerant), comparing the patch's changed lines
  to the commit's changed lines.
- **Parse failure:** if the model's output is not a parseable unified diff, both
  overlaps are **0** for that run, and the parse-failure rate is reported
  **separately per arm** so a format problem is never hidden inside a low score.

Cost (equal across arms by construction) is recorded for the ledger.

## Pre-registered hypothesis

At an equal token budget, the redcon pack yields a **higher diff-overlap** than
naive retrieval, at identical cost by construction. This is a test of **selection
quality**, not adoption: if redcon's pack is a better map than a keyword top-N at
the same price, it should show here even though it did not help the multi-turn
agent decide to use it.

If redcon does **not** beat naive retrieval at equal budget, that is a strong
negative for the selection itself, independent of delivery.

## What it decides

- redcon > naive: selection quality is real; the product problem is delivery
  (pull adoption, push loop cost), not the pack. Reinforces shipping the pack
  through non-interactive, one-shot channels.
- redcon ~= naive: the pack's ranking is no better than cheap keyword retrieval on
  this terrain; a serious signal to revisit the scorer.

## Cost estimate

One model call per task/arm/repeat. With ~24 tasks x 3 arms x 3 repeats and a
budget-sized context (30k-120k input, small output), roughly a few hundred calls
at single-call cost; a rough order-of-magnitude of tens of dollars list-price. A
precise estimate accompanies the run request, and a 2-run calibration precedes the
full set, as in night 2.

## Guardrails

Same as the layer-2 harness: deterministic corpora, results and transcripts
kept, backups between passes, and hypotheses fixed before measurement. No runs
until this design is approved and a window is confirmed.
