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
