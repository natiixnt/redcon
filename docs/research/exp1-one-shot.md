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

## Results

Run of record: 96 valid cells (24 per condition: 2 arms x 2 corpora x 12 tasks
x 2 repeats, 24 = 12 tasks x 2 repeats per arm/corpus). All numbers below
recompute from `benchmarks/agentic/results/oneshot-full/records.jsonl`, committed
with this PR; the full model responses are archived at
`~/redcon-exp-backups/exp1-oneshot-transcripts.tar.gz` (64K, 96 files). Total
list-price cost: $99.72. `empty_result` = 1 of 96 cells (one small-corpus redcon
cell, `56c7b8d`, returned an empty response; it is a parse failure scored zero per
the convention below, so metrics are unaffected). The tool-less `--tools ""`
config leaves the model nothing to do but answer, so parse failures are genuine
non-diff responses, not spent-on-a-tool-attempt turns.

### Metric definitions used below

- **file-overlap / line-overlap:** as defined above (file-level = |files(P) and GT|
  / |GT|; line-level = whitespace-tolerant hunk-line intersection).
- **Parse failure counts as zero.** A cell whose response is not a parseable
  unified diff scores file-overlap 0 and line-overlap 0 and is included in the
  unconditional means. Parse rate is reported separately so the two effects
  (does it produce a diff at all; is the diff on-target) are never conflated.
- **input (cacheCreate):** mean `cacheCreationInputTokens` per cell - the injected
  context lands there on the single call, so it is the honest per-arm input size.
- **efficiency:** unconditional file-overlap per 100k input tokens (cacheCreate).

### Primary result (unconditional, parse-failure = 0)

| corpus | arm | file-ov | line-ov | parse rate | input (cacheCreate) | eff (fo/100k) | cost |
|---|---|---|---|---|---|---|---|
| small | redcon | 0.271 | 0.039 | 12/24 (0.50) | 64k | 0.424 | $0.53 |
| small | naive | 0.521 | 0.134 | 18/24 (0.75) | 80k | 0.648 | $0.63 |
| heavy | redcon | 0.122 | 0.020 | 13/24 (0.54) | 197k | 0.062 | $1.51 |
| heavy | naive | 0.118 | 0.006 | 9/24 (0.38) | 203k | 0.058 | $1.48 |
| pooled | redcon | 0.196 | 0.029 | 25/48 (0.52) | 130k | 0.151 | $1.02 |
| pooled | naive | 0.319 | 0.070 | 27/48 (0.56) | 142k | 0.226 | $1.06 |

- **Small repos:** naive wins on raw overlap (0.521 vs 0.271) and on efficiency
  (0.648 vs 0.424). Whole files give the model exact code to edit; redcon's
  symbol-compressed selection costs exact-edit fidelity where naive can afford
  whole files.
- **Heavy repos:** a tie on raw overlap (redcon 0.122 vs naive 0.118), redcon
  marginally ahead on efficiency, and redcon's parse rate higher (0.54 vs 0.38).

### Conditional-on-parse overlap (exploratory, not pre-registered)

Overlap among only the cells that produced a valid diff:

| corpus | arm | n parsed | file-ov \| parsed | line-ov \| parsed |
|---|---|---|---|---|
| small | redcon | 12/24 | 0.542 | 0.078 |
| small | naive | 18/24 | 0.694 | 0.178 |
| heavy | redcon | 13/24 | 0.225 | 0.036 |
| heavy | naive | 9/24 | 0.315 | 0.016 |

**Decomposition, stated plainly:** redcon's heavy-corpus parity on the
unconditional metric (0.122 vs 0.118) is carried by its higher parse rate
(13/24 vs 9/24), **not** by per-parse selection quality - among diffs that
actually parse, naive is ahead even on heavy (0.315 vs 0.225). Redcon pulls
even because it commits to a valid diff more often on large repos, not because
what it selected was edited better.

### On the equal-budget premise

The budget target is equal by construction, but realized input is not identical.
On the **small corpus the redcon arm injects less than naive (64k vs 80k)**: the
compressed pack of a small repository saturates below the budget target (there is
not enough ranked, compressible material to fill it), whereas naive keeps adding
whole files until the budget is reached. On the heavy corpus the two are close
(197k vs 203k). This refines the equal-budget claim to: equal target, realized
input equal on heavy and lower for redcon on small.

Calibration correction, kept on the record: a single-task re-calibration had
suggested naive *under*-fills on large repos (183k vs 240k on one django task).
That did not generalize - at scale naive fills to budget on both corpora (small
80k, heavy 203k). Measuring realized per-arm input rather than asserting equality
was the right call.

### Compression asymmetry (the tradeoff this experiment measures)

Redcon fits more files, each partial (symbol extraction with line ranges); naive
fits fewer files, each whole. That asymmetry is inherent to what redcon does and
it cuts both ways by repo size: partial-but-more helps nothing for exact one-shot
edits on a small repo where whole-file naive dominates, and only reaches parity
(via parse rate) on a large repo where naive cannot fit enough whole files.

### Bottom line

Redcon's layer-1 selection quality (97.8% file recall) does **not** convert into
one-shot edit superiority over cheap keyword retrieval at equal budget. It is
behind on small repos and at parity-with-a-parse-edge on heavy repos. No claim of
end-task edit-quality improvement is made or supported here.
