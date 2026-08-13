# Experiment 3 design: adaptive rendering

Status: **design only, pre-registered. No runs until this design is approved and
Natalia confirms a usage window.**

## Motivation

Experiment 1 found that at equal budget redcon's compressed pack does not beat a
naive whole-file keyword retrieval in a one-shot, tool-less call: naive wins on
small repos and the two only tie on heavy repos, a tie carried by redcon's higher
parse rate rather than by per-parse selection quality. The visible difference was
the render *format*, not the *ranking*: naive delivered whole files the model
could edit exactly, while redcon delivered symbol-compressed fragments. Adaptive
rendering (see the adaptive rendering change and `redcon/compressors/
context_compressor.py`) keeps redcon's ranking but delivers each file whole when
it fits the budget, compressing only on overflow. Experiment 3 tests whether that
format change is what redcon's selection needed.

## Design

### Arm W

Arm W is the **identical Experiment 1 harness**, changed in exactly one place:
`redcon_context` is built from **adaptive-mode** pack output instead of the
compressed default. That output comes through the **public pipeline call**
(`run_pack(..., render_mode="adaptive")` via the same `redcon.core.pipeline`
entry Experiment 1 uses), **not** a benchmark-local shortcut, so arm W exercises
exactly the shipped adaptive path. Records include the per-task
whole-vs-compressed delivery fractions read from the pack artifact's per-entry
`delivery` field. Everything else is held fixed:

- Same 24 tasks (12 small from the night-1 pilot, 12 heavy from django and sympy),
  pinned in `benchmarks/agentic/tasks-oneshot.jsonl`.
- 2 repeats per task, equal size-scaled budget per repo.
- Tool-less single call via `--tools ""`, forced unified-diff response.
- Resumable and session-limit aware (stop cleanly on the cap, resume the missing
  cells with no duplication), backups after each pass.

### Controls (drift)

Before the run, check `claude --version` against the Experiment 1 version
(2.1.220).

- **Unchanged:** reuse the Experiment 1 `naive` and `redcon-compressed` data
  directly; W is the only arm run.
- **Drifted:** re-run `naive` as a concurrent control on the same tasks and label
  the comparison to `redcon-compressed` with an explicit drift caveat. Do **not**
  re-run `redcon-compressed` unless the drift is a major version.

### Metrics

Identical to Experiment 1, computed the same way:

- **file-overlap** and **whitespace-tolerant line-overlap**, with
  **parse-failure counted as zero** and parse rate reported separately.
- **per-arm input** via `cacheCreationInputTokens`, and **efficiency** as
  file-overlap per 100k input tokens.
- **list-price cost.**
- **Conditional-on-parse overlap** as the standing exploratory secondary
  (overlap among only the cells that produced a valid diff).
- **New mechanism metric:** per-task fraction of files delivered whole vs
  compressed (from the pack's per-entry `delivery` field), so W's behaviour is
  auditable and the degree of whole-file delivery is visible per corpus.

## Pre-registered hypotheses

- **H1:** W file-overlap **>= naive**, pooled and per corpus (ranking does not
  hurt once the format is equal).
- **H2:** W beats **redcon-compressed** on file-overlap and line-overlap (format,
  not ranking, was the drag).
- **H3:** W parse rate on heavy **>= naive** parse rate on heavy (the
  commit-to-a-valid-diff edge survives the format change).

### Four-outcome interpretation (fixed before the run)

- **All three hold:** adaptive becomes the default in the next release, with this
  measurement cited.
- **H1 fails:** positioning stays cost-and-determinism only, no quality claim,
  adaptive stays optional.
- **H2 fails:** compression was not the drag; no default change, investigate
  before further spend.
- **Mixed:** exploratory analysis only, no default change without a follow-up
  decision.

## Cost expectation

About 48 cells (24 tasks x 2 repeats, arm W only when there is no drift). A precise
projection accompanies the run request. If the projection exceeds roughly twice
the Experiment 1 per-cell cost, stop and report before spending. Reporting order:
the both-perspective report (raw overlap and overlap-per-input-token, per corpus,
with parse rate, per-arm input and the whole-vs-compressed mechanism metric) comes
to review **before** any Experiment 3 results PR.

## Guardrails

Same as Experiment 1: deterministic corpora, results and transcripts kept, backups
between passes, hypotheses and interpretation fixed before measurement. No runs
until this design is approved and a window is confirmed.

## Results

Run of record: 48 valid cells (24 tasks x 2 repeats, arm W only). CLI 2.1.220,
model claude-sonnet-5, no drift, so the Experiment 1 `naive` and
`redcon-compressed` data is reused directly. All numbers recompute from
`benchmarks/agentic/results/exp3-full/records.jsonl` (committed with this PR)
against the Experiment 1 records in
`benchmarks/agentic/results/oneshot-full/records.jsonl`. Total list-price cost:
**$49.88**, the sum of `total_cost_usd` over all 48 valid cells (transient-failure
retries were dropped by the resume, so the file holds only valid cells and the two
sums agree).

Metric definitions are identical to Experiment 1: file-overlap and
whitespace-tolerant line-overlap with **parse failure counted as zero**, parse rate
reported separately, per-arm input via `cacheCreationInputTokens` (cc), efficiency
as file-overlap per 100k input tokens, list-price cost. Conditional-on-parse
overlap (over cells that produced a valid diff) is the standing exploratory
secondary. The new mechanism metric is the per-task whole-vs-compressed delivery
fraction from the pack artifact's `delivery` field.

### Primary result (raw, per-input-token, parse; parse failure = 0)

| arm | corpus | file-ov | line-ov | parse | input (cc) | eff (fo/100k) | cost | cond-parse fo / lo (n) |
|---|---|---|---|---|---|---|---|---|
| W adaptive | small | 0.656 | 0.141 | 0.92 | 79k | 0.827 | $0.66 | 0.716 / 0.154 (22) |
| W adaptive | heavy | 0.208 | 0.048 | 0.62 | 184k | 0.113 | $1.42 | 0.333 / 0.077 (15) |
| W adaptive | pooled | 0.432 | 0.095 | 0.77 | 131k | 0.329 | $1.04 | 0.560 / 0.123 (37) |
| naive | small | 0.521 | 0.134 | 0.75 | 80k | 0.648 | $0.63 | 0.694 / 0.178 (18) |
| naive | heavy | 0.118 | 0.006 | 0.38 | 203k | 0.058 | $1.48 | 0.315 / 0.016 (9) |
| naive | pooled | 0.319 | 0.070 | 0.56 | 142k | 0.226 | $1.06 | 0.568 / 0.124 (27) |
| redcon-compressed | small | 0.271 | 0.039 | 0.50 | 64k | 0.424 | $0.53 | 0.542 / 0.078 (12) |
| redcon-compressed | heavy | 0.122 | 0.020 | 0.54 | 197k | 0.062 | $1.51 | 0.225 / 0.036 (13) |
| redcon-compressed | pooled | 0.196 | 0.029 | 0.52 | 130k | 0.151 | $1.02 | 0.377 / 0.056 (25) |

W wins on both perspectives, raw and per-input-token, pooled and per corpus. On
heavy it delivers more overlap (0.208 vs naive 0.118) at fewer input tokens (184k
vs 203k). The one place naive is ahead is a single conditional-on-parse cell:
small-corpus **line**-overlap given a parse, naive 0.178 vs W 0.154 - reported here
so the per-parse picture is not overstated.

### Mechanism metric: whole vs compressed

W delivered files whole at fraction: **small 0.672, heavy 0.789, pooled 0.730.**
Adaptive delivers most files whole (heavy repos more so, because django and sympy
source files are individually small and fit the 120k budget whole; the compressed
minority are large or generated files that do not fit).

### Paired per-cell analysis (exploratory, not pre-registered)

Same (sha, repeat) cell compared directly on file-overlap (win / loss / tie; ties
are mostly 0-0, i.e. neither arm touched a ground-truth file):

| comparison | pooled | small | heavy |
|---|---|---|---|
| W vs naive | 13 / 5 / 30 (0-0 ties: 14) | 5 / 1 / 18 | 8 / 4 / 12 |
| W vs redcon-compressed | 20 / 5 / 23 (0-0 ties: 15) | 11 / 0 / 13 | 9 / 5 / 10 |

W wins more cells than it loses against both arms, with a large tie mass driven by
the many 0-0 cells (both arms miss in one shot on hard tasks). Against compressed,
W never loses a small-corpus cell (11 / 0 / 13).

### Hypotheses against the pre-registered interpretation

- **H1 (W file-overlap >= naive, pooled and per corpus): HELD.** Pooled 0.432 vs
  0.319; small 0.656 vs 0.521; heavy 0.208 vs 0.118. Ranking does not hurt once the
  format is equal.
- **H2 (W beats redcon-compressed on file-overlap and line-overlap): HELD.** File
  0.432 vs 0.196, line 0.095 vs 0.029 pooled, and in both corpora. The render
  format, not the ranking, was the drag.
- **H3 (W parse rate on heavy >= naive parse rate on heavy): HELD.** 0.62 vs 0.38.

All three hold, so per the pre-registered interpretation **adaptive becomes the
default in the next release, with this measurement cited.**

The decomposition is clean: conditional-on-parse, W is level with naive (0.560 vs
0.568 pooled) and both far exceed compressed (0.377), so the whole-file format
closes the per-parse quality gap (H2). W's unconditional edge over naive comes from
a higher parse rate (0.77 vs 0.56 pooled), i.e. redcon's ranking makes the model
commit to a valid diff more often (H1, H3). Format and ranking together.

### Scope

This is one-shot selection quality (Experiment 1's frame), not multi-turn end-task
value. Night 2 closed the multi-turn question and nothing here reopens it. The
claim is precisely: at equal budget, adaptive-rendered redcon beats both cheap
keyword retrieval and compressed redcon on one-shot edit fidelity. No multi-turn
end-task quality improvement is claimed.
