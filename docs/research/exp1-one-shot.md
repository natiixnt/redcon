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

- **Corpora:** `tasks-heavy.jsonl` (django, sympy) plus 12 tasks from the small
  corpus for contrast.
- **Metric:** edit correctness as **diff overlap** between the model's proposed
  patch and the real commit's diff (line- and file-level), plus the (equal) cost
  for the record.
- **Model:** sonnet, single call, deterministic prompt; a few repeats for
  variance.

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
