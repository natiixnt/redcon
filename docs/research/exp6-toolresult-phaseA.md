# Experiment 6 Phase A: tool-result compression ceiling (offline)

Status: **closed at Phase A. Offline analysis only, no agent spend, no product
change. The safe savings ceiling does not clear the pre-registered bar, so there
is no Phase B.**

## Idea under test

Pull (pre-injecting a redcon pack, Exp 1/2) did not beat naive retrieval and push
(mid-session injection) also failed. Both add context the agent did not ask for.
The third delivery channel is different in kind: intercept the tool **results**
the agent already requested (Read, Grep, test output, git diff) and compress them
harness-side before they re-enter context. Because it only shrinks what the agent
already pulled, the token cost strictly drops; the only open question is whether
compression discards something the agent later needs. Phase A estimates the
savings ceiling and the safety floor from existing data, with no new runs.

## Method

Source: the 228 night-2 stream-json transcripts (`results/agent-heavy`,
backed-up tarball), all six arms, model claude-sonnet-5. For each run we pair
every `tool_use` with its `tool_result` by id, record the assistant turn that
made each call, classify the call (read / grep / pytest / git_* / listing /
bash_other / other), and re-render each result offline through redcon's existing
machinery where it applies:

- **Reads** through the shipped adaptive rule: whole when the line-stripped body
  is at or below `full_file_threshold_tokens` (300), otherwise
  `select_symbol_aware_chunks` at an 80-line budget keyed on the task keywords.
- **Command output** (grep, git diff/log/status, pytest, listing) through
  `redcon.cmd.detect_compressor` and its schema-aware compressors, with a fixed
  `BudgetHint(remaining_tokens=8000, max_output_tokens=4000)` so large outputs
  compact and small ones stay verbose. The hint is stated for reproducibility.

Tokens are counted with the standard `estimate_tokens` estimator, same call for
original and compressed. Runs are keyed `(sha, phrasing, repeat)`; the baseline
arm has 48 runs (12 tasks x {medium-r0, precise-r0, precise-r1, precise-r2}), of
which 36 are precise. The **precise slice is primary**: the offline read
compression is keyed on the precise-phrasing keywords, so on precise runs the
keywords match the run and the estimate is internally consistent.

Costs use Sonnet 5 list pricing (base input $3, output $15 per MTok) with the 1h
ephemeral cache the runs actually used: a cache write is 2x base input ($6) and a
cache read is 0.1x ($0.30). A tool-result token that enters context at turn t is
priced as one cache write plus a cache read on each later turn it survives.

Safety is measured directly against later edits: for every file the agent
eventually edited, we locate the edited region in the body of its most recent
prior read and check whether that read's compressed rendering still contains the
eventually-edited lines (content match, whitespace-tolerant), split by whether
the read would have been delivered whole or compressed.

The analysis script is `benchmarks/agentic/exp6_toolresult_analysis.py`; its
records are `benchmarks/agentic/results/exp6-phaseA/` (`toolresult_rows.jsonl`,
`edit_coverage.jsonl`, `runs.jsonl`, `report.txt`). All 228 transcripts parse;
202 emitted at least one tool-result.

## Results

### Savings by tool type (baseline arm, primary)

Aggregate reduction over the baseline arm's re-rendered results:

| kind        |    n | orig_tok | comp_tok | pooled save | median-per-result |
|-------------|-----:|---------:|---------:|------------:|------------------:|
| read        |  226 |  216,965 |  139,528 |       35.7% |              0.0% |
| grep        |  369 |   79,750 |   58,597 |       26.5% |              0.0% |
| git_show    |   47 |   72,313 |   72,313 |        0.0% |              0.0% |
| bash_other  |  196 |   54,019 |   52,605 |        2.6% |              0.0% |
| git_log     |   46 |   10,828 |    8,582 |       20.7% |              9.5% |
| git_diff    |   17 |    5,477 |    1,950 |       64.4% |             83.6% |
| listing     |   23 |    4,328 |    3,285 |       24.1% |              0.0% |

The pooled savings sit on a few large results; the median result in every read
and grep bucket saves nothing. git_diff is the one kind that compresses reliably
per result (median 83.6%), but its total volume is tiny. git_show has no
compressor and passes through untouched, yet is the second-largest read-like
bucket.

### Per-run gross reduction (ceiling, includes unsafe read compression)

Keyed `(sha, phrasing, repeat)`, reduction of the run's own tool-result tokens:

| slice            | median | p25  | p75   |
|------------------|-------:|-----:|------:|
| precise (36, primary) | 17.3% | 4.5% | 25.2% |
| all baseline (48)     | 15.8% | 4.2% | 29.2% |

Percentiles are the value at the sorted zero-based index `floor(q * (n - 1))`
with no interpolation (the "lower" nearest-rank method); a linear-interpolation
percentile gives slightly different p25/p75.

This is a **ceiling that includes read compression**, which the safety result
below rules out. It is the most that a lossless-looking pass could remove from
the results channel, not what is safely realizable.

### Snapshot-delta ceiling (safe re-read channel)

The re-read volume, the token count of second-and-later reads of the same file
per run, is what a snapshot-delta harness could remove without touching any first
read: **median 420 tokens/run** (p75 964), a **median 3.8%** of the run's
tool-result tokens on the precise slice. 65% of baseline runs re-read some file
(mean max reads of one file 1.98). This is bounded but genuinely safe.

### Cost translation (precise slice, Sonnet 5 list pricing, 1h cache)

The safe channel is command-output compression plus snapshot-delta on re-reads,
each priced as a cache write plus later-turn cache reads:

| quantity | value |
|----------|------:|
| mean run cost | $1.2226 |
| mean safe savings | $0.0230 |
| - command output | $0.0121 |
| - snapshot-delta | $0.0109 |
| **safe savings as share of run cost** | **1.88%** |

Read-side re-reads and command output are both cheap in cache terms (a read
token costs one write plus 0.1x reads for its remaining turns), so even the full
re-read volume plus every schema-aware command saving lands under 2% of the run.

The mean run cost here is recomputed from each run's recorded token usage under
this pricing model, so it differs from the night-2 recorded `cost_usd`; the 1.88%
ratio applies the same model to both the cost and the savings, so it is internally
consistent regardless of that offset.

### Safety: edit-line coverage

Over 534 edited-file reads:

| read delivery | n | edited-lines-preserved |
|---------------|--:|-----------------------:|
| whole         | 328 | 100.0% |
| compressed    | 206 |  12.6% |
| overall       | 534 |  66.3% |

A whole read trivially keeps every line. A symbol-compressed read preserves the
lines the agent later edits only **12.6%** of the time: compressing a large read
destroys the eventually-edited content in roughly seven of every eight cases.
Read compression is the largest savings bucket and simultaneously the one that is
unsafe to touch.

### Grep-safety caveat

The edit-line safety test covers reads, because reads have a measurable
downstream signal (the later edit). Grep and search output have no comparable
offline ground truth: condensing a grep result can drop a path or line the agent
would have navigated to next, and that navigation harm is **not measured here**.
The command-output savings above should be read as an upper bound on a channel
whose safety is itself unestablished, not as a free saving.

## Decision: close at Phase A

The pre-registered gate for continuing was that the safe channels, snapshot-delta
plus command output, reach roughly 5% of run cost. They reach **1.88%**. The
result channel's volume sits almost entirely in reads, and read compression fails
the safety test at 12.6% edit-line survival, so the volume that is large is
exactly the volume that is unsafe to compress. What remains safe is small and, in
the grep case, of unestablished safety.

Exp 6 closes at Phase A as a **negative-ceiling result**. There is no Phase B.
The third delivery channel (compressing tool results the agent already pulled) is
recorded as closed in `docs/research/agentic-eval.md`: cost-free in principle,
but the realizable, safe saving is under 2% of run cost on this evidence, because
the compressible volume lives where compression destroys edit targets.
