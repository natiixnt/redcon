# Experiment 6 Phase A: tool-result compression ceiling (offline)

Status: **offline analysis complete. No agent spend, no product changes. Phase B
is not designed until this report is reviewed.**

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
backed-up tarball), all six arms. For each run we pair every `tool_use` with its
`tool_result` by id, classify the call (read / grep / pytest / git_* / listing /
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
original and compressed. Safety is measured directly against later edits: for
every file the agent eventually edited, we locate the edited region in the body
of its most recent prior read and check whether that read's compressed rendering
still contains the eventually-edited lines (content match, whitespace-tolerant),
split by whether the read would have been delivered whole or compressed.

The analysis script is `benchmarks/agentic/exp6_toolresult_analysis.py`; its
records are `benchmarks/agentic/results/exp6-phaseA/` (`toolresult_rows.jsonl`,
`edit_coverage.jsonl`, `report.txt`). All 228 transcripts parse; 202 emitted at
least one tool-result and contribute to the tables.

## Results

### Savings by tool type (baseline arm, primary)

Aggregate reduction over the baseline arm's 5369-token-weighted results:

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
and grep bucket saves nothing, because most reads are already small (whole) and
most greps are short. git_diff is the one kind that compresses reliably per
result (median 83.6%), but its total volume is tiny. git_show has no compressor
and passes through untouched, yet is the second-largest read-like bucket.

### Per-run reduction

Summing per baseline run, tool-result token reduction is **median 18.3%**
(p25 4.5%, p75 29.2%) of the run's own tool-result tokens. This is the ceiling on
what a lossless-looking harness pass could remove from the results channel, and
it is a share of tool-results, not of total input.

### Safety: edit-line coverage

Over 534 edited-file reads:

| read delivery | n | edited-lines-preserved |
|---------------|--:|-----------------------:|
| whole         | 328 | 100.0% |
| compressed    | 206 |  12.6% |
| overall       | 534 |  66.3% |

This is the decisive finding. A whole read trivially keeps every line. A
symbol-compressed read preserves the lines the agent later edits only **12.6%**
of the time: compressing a large read destroys the eventually-edited content in
roughly seven of every eight cases. Read compression is the largest savings
bucket and simultaneously the one that is unsafe to touch.

### Re-read exposure

146 of 203 runs (71.9%) read the same file more than once; the mean
maximum-reads-of-one-file is 2.27. Re-reads are a savings channel that never
touches first-read fidelity: on a repeat read the harness can return only the
delta from the prior read. It is bounded but safe, and it does not appear in the
per-run 18.3% above (that figure re-renders each read independently).

## Reading

The results channel is real but modest, and its savings and its risk are stacked
on the same bucket. The large, safe-looking pooled numbers on reads are an
artifact of a few big files; compressing those big reads is exactly what fails
the safety test at 12.6%. The genuinely safe savings are:

- schema-aware command output (grep, git_diff, git_log, listing): reliable where
  it fires, small in aggregate;
- snapshot-delta on re-reads: 72% of runs are exposed, first-read fidelity
  untouched.

Symbol-compressing reads is off the table on this evidence.

## Recommended Phase B pre-registration gates

Two gates, both computed from the offline data above, for the reviewer to accept
or move before any Phase B run:

1. **Savings gate.** A tool kind is a Phase B candidate only if its offline
   median-per-result reduction is at or above **25%**. This admits git_diff
   (83.6%) and is a near-miss for git_log (9.5% median despite 20.7% pooled);
   it excludes reads and grep, whose median result saves nothing. Read the gate
   on the median, not the pooled share, so a handful of large results cannot
   carry a kind in.
2. **Edit-line-coverage gate.** Any variant that compresses a read must preserve
   at least **95%** of eventually-edited lines offline. Symbol compression scores
   12.6% and fails decisively, so Phase B must not symbol-compress reads. Reads
   stay whole; the only read-side savings pursued is snapshot-delta on re-reads,
   which is lossless on first read by construction and so passes this gate
   trivially.

Net: Phase B, if it runs, is scoped to schema-aware command-output compression
plus re-read snapshot-delta, not read compression. No Phase B design work until
this report is reviewed.
