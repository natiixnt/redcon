# Agentic evaluation of redcon

A deterministic, pre-registered evaluation of redcon's context selection, on real
commits, at two layers: a redcon-only measurement of what the pack contains
(layer 1), and an agent-in-the-loop measurement of whether the pack changes
end-task outcomes (layers 2, "night 1" on small repos and "night 2" on large
ones). Every task is a real commit; the tool sees only the parent state, and the
files and line ranges the commit changed are the ground truth.

## Abstract

Layer 1, on redcon, httpx and click (1,890 runs), finds redcon's ranker recovers
the changed files with **97.8% recall (95% CI 97.3-98.3)** while shrinking the
context to a **mean 96% below the whole-repo baseline**. Layer 2 asks whether that
selection improves what an autonomous agent actually does. On small repos (night
1) it did not, and the failure was traced to adoption: the agent never called
redcon and grepped by hand. On large repos (night 2, django and sympy, 228 agent
runs) redcon delivered **no measured end-task improvement through any channel
tested**: the agent will not reach for it (0-11% adoption across three delivery
channels), and pre-injecting the pack does not beat baseline in a multi-turn loop
at any coverage (a 0.90-coverage 120k map ties recall at 3.4x cost, with a 33%
turn-cap rate; precision is intact once redcon's own build artifact is excluded).
A deterministic sweep shows the coverage ceiling is a **budget limit,
not a ranking limit** (pack file-hits climb 0.36 to 0.90 from 12k to 120k). Two
follow-up experiments closed the remaining delivery questions, both negative: at
equal budget redcon's selection does **not** beat cheap keyword retrieval in a
one-shot, tool-less call (Experiment 1), and injecting only the ranking list does
**not** beat baseline in a loop (Experiment 2). Redcon's demonstrated value is
therefore **deterministic, budget-capped, auditable packing with measured token
savings versus an agent reading the repository by hand (layer 1)** - not an
end-task quality improvement. Selection quality does not convert into one-shot
edit superiority over cheap keyword retrieval at equal budget, and push delivery
is closed for interactive use at any weight (full map, 120k, top-10 list). No
claim of end-task quality improvement is made anywhere in this evaluation.

## Setup

- **Corpora.** Layer 1 and night 1 use a pinned 210-task corpus from redcon
  (v1.15.0), httpx and click (small and medium repos). Night 2 uses a 12-task
  context-heavy corpus from django and sympy (multi-million-token repos), commits
  touching 3-8 files across >= 2 directories, 60-400 line diffs, stratified into
  small/medium/large by diff size. Both corpora are pinned to fixed SHAs and
  committed under `benchmarks/agentic/`.
- **Harness.** Each task is evaluated at the commit's parent state in a fresh git
  worktree, so nothing about the change can leak into selection. Layer 1 runs
  `redcon pack` with default config. Layer 2 runs the Claude Code CLI headless
  (`-p`, model sonnet, 30-turn cap) to implement the change, and records the
  tokens, list-price cost, turn count, edited files, and per-run `mcp__redcon__*`
  call count from the stream-json transcript.
- **Metrics.** *file recall* (changed files surfaced or edited), *region
  containment* (changed line ranges surfaced verbatim), *precision* (agent edits
  that are ground-truth files), *cost* (CLI list-price USD, a reported metric),
  *adoption* (runs that called a redcon tool), and *pack file-hits* (ground-truth
  files present in a pre-injected pack).

## Methods

Layer 1 is deterministic: the pack depends only on the parent state, the phrasing
and the budget, and means carry a seeded 95% bootstrap CI. Layer 2 is stochastic
(the model is not seeded; repeats gauge variance) and draws on subscription usage,
so it is run deliberately and never in CI. Hypotheses and interpretations were
pre-registered before each pass (see `results/agent-heavy/NIGHT2.md`), including
the four-outcome interpretation table, the two-channel framing for the config arm,
the push-vs-pull thesis, and the arm-P and arm-P120 hypotheses, so no narrative is
fitted after the fact.

## Results

### Layer 1: what the pack contains (small and medium repos)

| cut | file recall (95% CI) | region containment (95% CI) |
|---|---|---|
| overall | 97.8% [97.3, 98.3] | 37.1% [35.5, 38.8] |
| budget 12k / 30k / 60k | 95.4 / 98.5 / 99.6% | 35.8 / 37.3 / 38.2% |

Context reduction from the whole-repo baseline averages 96% (95.6-97.4% across
budgets). Wording sensitivity is reported on the distinguishable subset only
(medium collapses onto precise when the subject names no file or symbol). The
pack finds the right files and surfaces about a third of the exact changed lines
verbatim; it is a map with partial content, not the full text.

### Night 1: agent arm on small repos - no end-task benefit

Twelve tasks x 2 arms x 3 repeats. Redcon (available via MCP) did not beat
baseline: recall 0.61 vs 0.69 at parity cost. The one clear loss (redcon/56c7b8d)
was audited from the transcript: the agent called redcon **zero** times, ran ~17
Bash grep sweeps, and capped out, while layer 1 confirms the pack ranked all four
changed files. The failure is behavioural (adoption), not ranking.

### Night 2: agent arm on large repos - no value through any channel

228 runs. Arms: **B** baseline (no MCP), **A** redcon MCP unprompted, **Ag** plus
a one-line prompt hint, **Agc** plus the rule in CLAUDE.md, **P** pre-inject a 30k
pack, **P120** pre-inject a 120k pack.

Precision is the corrected value (2026-08-11): the pack build wrote redcon's own
`.redcon*` cache artifacts into the worktree, which inflated the edited-file set
for the pack-building arms (P, P120, and the 4 adopting Agc runs) and deflated
their precision; excluding `.redcon*` and averaging over runs that edited a real
file gives the numbers below. Push fails on cost and recall, not precision.

| arm | cost/run | recall | precision | adopted |
|---|---|---|---|---|
| B baseline | $0.78 | 0.688 | 0.872 | 0/36 |
| A redcon | $0.82 | 0.618 | 0.897 | 0/36 |
| Ag guided | $0.91 | 0.617 | 0.862 | 0/36 |
| Agc config | $0.69 | 0.588 | 0.846 | 4/36 |
| P (30k) | $1.84 | 0.634 | 0.916 | 0/36 |
| P120 (120k) | $2.72 | 0.575 | 0.829 | 0/24 |

- **Pull fails on delivery.** Adoption is 0/36 unprompted, 0/36 with a prompt
  line, and 4/36 via the CLAUDE.md rule - the only channel with any uptake. (The
  installer writes AGENTS.md, which headless Claude Code does not read; only
  CLAUDE.md is read - a shipped-guidance delivery bug.) The guided arm was the
  single worst: unheard guidance sent the agent searching more, not ranking.
- **Push fails in the loop, at any coverage.** Pre-injection does not beat
  baseline at 30k (0.64 coverage; recall 0.634 vs 0.688 at 2.4x cost) or at 120k
  (0.90 coverage; recall ties B excluding cap-outs, at 3.4x cost and a 33%
  turn-cap rate). Precision is intact once the `.redcon` build artifact is
  excluded (P 0.916, P120 0.829 vs B 0.872); push fails on cost and recall, not
  precision. The incomplete 30k map lowers recall (the agent trusts it), not
  precision. The pre-registered context-window caveat did not trigger: failures
  were turn-caps, not truncation.

The injected map's cost scales with turns (the 30k/120k prefix is re-read every
turn), so any value push might carry is confined to short, non-interactive flows -
which these multi-turn runs do not cover.

### Coverage sweep: budget, not ranking

Deterministic layer-1 packs over the heavy corpus:

| budget | 12k | 30k | 60k | 120k |
|---|---|---|---|---|
| pack file-hits | 0.358 | 0.627 | 0.738 | 0.896 |

Coverage climbs toward ~1.0, so the default 30k pack under-covers multi-million-
token repos because of budget, not ranking. redcon finds the files given tokens.

## Threats to validity

- The adoption result is specific to **headless autonomous mode** (`claude -p`)
  with **model sonnet**. An interactive user can invoke the tools directly, and
  other models may have different tool-use habits; the claim is "the autonomous
  sonnet agent does not reach for redcon on its own here", not "agents never use
  redcon".
- Layer 2 is stochastic with modest n (n=36 per precise arm, n=24 for P120); the
  pfh=1.0 subset lead (n=6) was flagged post-hoc and then refuted by P120.
- The heavy corpus is 12 tasks from two repos; diffs are 60-400 lines, so the
  "large" band is large for these repos, not for the whole of open source.
- Layer-1 selection quality does not imply end-task value; measuring that gap is
  the point of layer 2.

## Registered questions: resolved

The two directions registered above were run and both came back negative.

1. **Single- and few-turn flows (Experiment 1, one-shot selection quality).**
   Resolved: **negative.** A single tool-less model call per task, redcon's
   compressed pack content versus a pinned naive whole-file keyword retrieval at
   equal budget (96 valid cells, 24 per condition). On small repos naive wins on
   raw overlap (0.521 vs 0.271) and efficiency; on heavy repos the two tie on raw
   overlap (0.122 vs 0.118), a tie carried by redcon's higher parse rate (13/24 vs
   9/24), not per-parse selection quality (conditional overlap 0.225 vs 0.315).
   Redcon's layer-1 selection quality does not convert into one-shot edit
   superiority over cheap keyword retrieval. Full data and tables:
   `docs/research/exp1-one-shot.md`.
2. **P-lite (Experiment 2, inject the ranking not the map).** Resolved:
   **negative on end-task value.** Injecting only the top-10 ranking list (about
   145 tokens) then running the agent normally (24 valid runs vs the reused
   night-2 baseline B) held cost (0.66 vs 0.78) but did not beat baseline on recall
   (0.556 vs 0.688). Precision is **intact** (0.943 vs 0.872 with redcon's own
   `.redcon` build artifact excluded - see the correction in exp2-p-lite.md), so
   the pre-registered no-precision-collapse hypothesis holds; the loss is on recall
   and cost. The injected list covered only 27% of the ground-truth files, so it
   **narrowed exploration** (17.8 vs 19.8 turns) and lowered recall rather than
   anchoring edits onto wrong files. Push delivery is closed for interactive use at
   any weight (full map, 120k, top-10 list), on cost and recall grounds. Full data:
   `docs/research/exp2-p-lite.md`.

## Open questions (registered)

One direction the data points to but does not settle:

1. **Adaptive rendering (Experiment 3).** Experiment 1 found that on heavy repos
   redcon only reaches parity via parse rate, and that naive's advantage rode on
   delivering whole files the model could edit exactly, while redcon delivered
   symbol-compressed fragments. That isolates a testable hypothesis: the drag was
   the render *format*, not the *ranking*. Adaptive rendering walks the same
   ranking order but includes each file whole when it fits the remaining budget
   and falls back to the compressed entry only on overflow (see the adaptive
   rendering change and `docs/research/exp3-adaptive-rendering.md`). Arm W reuses
   the Experiment 1 harness unchanged (same 24 tasks, 2 repeats, equal budget,
   tool-less single call, forced unified diff) with `redcon_context` built from
   adaptive-mode output. Pre-registered hypotheses:
   - **H1:** W file-overlap >= naive, pooled and per corpus (ranking does not hurt
     once the format is equal).
   - **H2:** W beats redcon-compressed on file-overlap and line-overlap (format,
     not ranking, was the drag).
   - **H3:** W parse rate on heavy >= naive parse rate on heavy (the
     commit-to-a-valid-diff edge survives the format change).

   Interpretation is fixed before the run: all three hold and adaptive becomes the
   next release default with the measurement cited; H1 fails and positioning stays
   cost-and-determinism only with adaptive optional; H2 fails and compression was
   not the drag, so no default change and investigate before further spend; mixed
   is exploratory only, no default change without a follow-up decision.

## Reproduce

Layer 1 is deterministic and free of API cost:

```bash
python benchmarks/agentic/run.py --out-dir benchmarks/agentic/results
```

The coverage sweep (also deterministic):

```bash
python benchmarks/agentic/coverage_sweep.py --cache ~/.cache/redcon-agentic-heavy
```

The layer-2 agent arms require the Claude Code CLI and draw on subscription usage;
see `benchmarks/agentic/agent_arm.py` and the pinned `NIGHT1.md` / `NIGHT2.md` for
exact invocations and per-run records.
