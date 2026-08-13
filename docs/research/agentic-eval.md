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
not a ranking limit** (pack file-hits climb 0.36 to 0.90 from 12k to 120k). Five
follow-up experiments closed the delivery picture. Two are negative: injecting only
the ranking list does not beat baseline in a multi-turn loop (Experiment 2), and
redcon's default **compressed** pack does not beat cheap keyword retrieval in a
one-shot, tool-less call (Experiment 1). The third is the program's **first
positive**: **adaptive rendering** - redcon's same ranking delivered as whole files
when they fit the budget, compressing only on overflow - **beats both naive keyword
retrieval and compressed redcon on one-shot edit fidelity at equal budget**
(Experiment 3; file-overlap 0.432 vs 0.319 vs 0.196 pooled). The mechanism is clean:
per-parse quality matches naive (the whole-file format closes the gap that
compression opened), and redcon's edge comes from a higher parse rate (its ranking
makes the model commit to a valid diff more often). The fourth refines the largest
repos: **tiered rendering** (top files whole, a compressed tail) recovers the heavy
ground-truth coverage adaptive gave up (0.756 vs 0.363) and lifts the heavy parse
rate, clearing all three pre-registered bars, but the file-overlap gain is modest
and heavy-only with a line-overlap trade (Experiment 4, held with nuance). The
product outcome is a size-gated adaptive-v2, not a uniform change. The fifth tests
a third delivery channel, **compressing the tool results the agent already pulled**:
an offline ceiling on the night-2 transcripts closes it at Phase A, because the
compressible volume lives in reads where compression preserves the eventually-edited
lines only 12.6 percent of the time, leaving a safe saving of 1.88 percent of run
cost (Experiment 6, negative ceiling, no agent run). Redcon's
demonstrated value is
therefore **deterministic, budget-capped, auditable packing with measured token
savings versus an agent reading the repository by hand (layer 1), plus a one-shot
selection-quality advantage once the pack is rendered adaptively (Experiment 3)**.
That advantage is scoped strictly to **one-shot and few-turn, non-interactive
flows**; the multi-turn end-task negatives (night 1, night 2) stand, and no
multi-turn end-task quality improvement is claimed anywhere in this evaluation.

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
3. **Adaptive rendering (Experiment 3).** Resolved: **positive - the program's
   first.** Experiment 1 traced redcon's one-shot gap to the render *format* (it
   delivered symbol-compressed fragments while naive delivered whole files), not
   the *ranking*. Adaptive rendering keeps redcon's ranking but delivers each file
   whole when it fits the budget, compressing only on overflow. Arm W (the same
   Experiment 1 harness with adaptive-mode context, 48 valid cells, no CLI drift)
   confirms all three pre-registered hypotheses: **H1** W file-overlap beats naive
   pooled and per corpus (0.432 vs 0.319; 0.656 vs 0.521 small; 0.208 vs 0.118
   heavy); **H2** W beats compressed on both file- and line-overlap (0.432 vs 0.196,
   0.095 vs 0.029); **H3** W heavy parse rate beats naive (0.62 vs 0.38). The
   decomposition is clean: conditional-on-parse, W matches naive (0.560 vs 0.568)
   and both far exceed compressed (0.377), so the whole-file format closes the
   per-parse quality gap, while W's edge over naive is a higher parse rate - redcon's
   ranking makes the model commit to a valid diff more often. At equal budget,
   adaptive-rendered redcon beats both cheap keyword retrieval and compressed redcon
   on one-shot edit fidelity. Per the pre-registered interpretation, adaptive becomes
   the next-release default. Full data: `docs/research/exp3-adaptive-rendering.md`.
4. **Tiered rendering (Experiment 4).** Resolved: **held with nuance; product
   outcome is a size-gated adaptive-v2.** A decomposition of Exp 3 showed adaptive
   bought whole-file fidelity by spending its budget on whole files, dropping heavy
   ground-truth coverage (0.363 vs compressed's 0.896). Tiered rendering reserves
   budget for a compressed tail; a deterministic dev-corpus sweep (disjoint from the
   held-out 24) picked `topk:10` (top files whole, the rest compressed). Arm W2 on
   the held-out 24 confirms all three pre-registered hypotheses: **H1** W2 heavy
   file-overlap > adaptive (0.235 vs 0.208); **H2** W2 heavy pack-GT-coverage >= 0.7
   (0.756, recovered from 0.363); **H3** W2 small file-overlap >= 0.606 (0.625).
   Honestly, the heavy win is modest and parse-rate-driven: W2 lifts the heavy parse
   rate to 0.92 (vs 0.62) and coverage to 0.756, so the model commits to a valid diff
   more often, but per-parse fidelity is lower (0.256 vs 0.333) and heavy line-overlap
   trades down (0.026 vs 0.048, fewer whole files); small file-overlap is marginally
   below adaptive with line-overlap above; pooled file-overlap is essentially tied
   (0.430 vs 0.432). Because the gain is heavy-only and mixed, the product outcome is
   **not a uniform flip** but a **size-gated adaptive-v2**: plain adaptive stays for
   repos below the top budget band, and only in the top band (estimated repo tokens
   over 3M, the 120k-budget regime measured here) adaptive applies `topk:10`
   internally. Middle bands (45k/75k budgets) stay plain adaptive; that regime is
   unmeasured. Full data: `docs/research/exp4-tiered-rendering.md`.
5. **Tool-result compression (Experiment 6, third delivery channel).** Resolved:
   **closed at Phase A, negative ceiling.** Pull and push both add unrequested
   context; the third channel instead compresses the tool results the agent
   already asked for (Read, Grep, test output, git diff), so cost strictly drops
   and only quality is at stake. An offline re-render of the 228 night-2
   transcripts through redcon's existing machinery put the ceiling below the bar:
   per-run tool-result reduction is a median 17.3 percent (precise slice), but the
   volume sits in reads, and a symbol-compressed read preserves the lines the
   agent later edits only **12.6 percent** of the time, so read compression is
   unsafe. The safe channels alone (schema-aware command output plus snapshot-delta
   on re-reads) are **1.88 percent** of the mean run cost under the cache pricing
   model, short of the pre-registered ~5 percent gate, so there is no Phase B. Grep
   condensation was not counted as safe: its navigation harm is unmeasured. Full
   data: `docs/research/exp6-toolresult-phaseA.md`.

## Open questions (registered)

One registered question remains gated, not run:

1. **Line-numbered whole files (Experiment 4 second question).** Render whole files
   with line-number prefixes so the model can anchor exact `@@` hunks (line-overlap
   is low even when file-overlap is high, and the tiered heavy win came at a
   line-overlap cost). Registered with a cost note (a second arm, roughly one more
   48-cell pass); it is not bundled into any run and needs its own pre-registration
   and window.

The delivery picture is otherwise closed: one-shot compressed selection does not
beat naive (Exp 1, negative); ranking-list push does not beat baseline in a loop
(Exp 2, negative); adaptive rendering beats both naive and compressed on one-shot
edit fidelity (Exp 3, positive); size-gating adaptive to tiered `topk:10` on the
largest repos recovers heavy coverage and parse rate at a line-overlap trade (Exp 4,
held with nuance); and compressing the tool results the agent already pulled saves
too little safely to pursue (Exp 6, closed at Phase A, negative ceiling). All wins
are scoped strictly to one-shot and few-turn, non-interactive flows; the multi-turn
end-task negatives from night 1 and night 2 stand and are not reopened.

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
