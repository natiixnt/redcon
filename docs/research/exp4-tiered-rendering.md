# Experiment 4 design: tiered rendering (adaptive-v2)

Status: **design and dev-corpus sweep only, pre-registered. No agent runs until
this design is approved and Natalia confirms a usage window.**

## Motivation

Experiment 3 made adaptive rendering the default: deliver each ranked file whole
when it fits the budget, compress on overflow. But a decomposition of the Exp 3
records shows adaptive bought whole-file fidelity by spending its whole budget
early, at the cost of ground-truth coverage. On the heavy corpus:

- Compressed packs contained the ground truth almost fully (pack-GT-coverage
  0.896, 18/24 cells complete) but scored file-overlap 0.122.
- Adaptive traded coverage down to 0.363 (0/24 complete) for file-overlap 0.208.
- The 6 heavy cells where adaptive happened to keep high coverage scored
  file-overlap 0.423 at parse rate 0.83.

So both matter: coverage (having the ground-truth files at all) and whole-file
fidelity (being able to edit them exactly). Tiered rendering aims for
compressed-level coverage with whole-file fidelity for the top-ranked files, by
reserving part of the budget for compressed entries instead of spending it all on
whole files.

## Tiered policies (dev only, not user-visible)

Implemented behind the adaptive mode as an internal `[compression].tiered_policy`
knob (no CLI or `[render]` surface, empty by default = plain adaptive). Each policy
is a deterministic two-pass walk in ranking order with the same token estimator;
every entry records its delivery form (whole or compressed):

- `split:<frac>` - whole files fill a sub-budget of `frac * max_tokens` in ranking
  order; every remaining file is compressed into the rest of the budget.
- `topk:<int>` - the top K ranked files are delivered whole (if they fit); the rest
  are compressed.
- `score:<float>` - files with a ranking score at or above the threshold are
  delivered whole (if they fit); the rest are compressed.

## Dev corpus (held-out discipline)

Tuning is on `benchmarks/agentic/tasks-exp4-dev.jsonl`: a fresh 12 small + 12 heavy
tasks mined by `benchmarks/agentic/build_exp4_dev.py`, stratified 4/4/4 by diff
size, **disjoint from the 24 held-out one-shot tasks** in `tasks-oneshot.jsonl`
(verified: zero SHA overlap). The held-out 24 are never used for policy selection.

## Sweep results (deterministic, no agent spend)

From `benchmarks/agentic/exp4_sweep.py` over the dev corpus at the standard
size-scaled budgets (`results/exp4-sweep/sweep.jsonl`), per policy per corpus:
pack-GT-coverage, the fraction of ground-truth files delivered whole, files
included, and budget use. No policy exceeded budget on any of the 192 packs.

| policy | corpus | GT-cov | GT-whole | files | budget |
|---|---|---|---|---|---|
| compressed | small | 1.000 | 0.000 | 177 | 0.52 |
| compressed | heavy | 0.896 | 0.000 | 590 | 0.97 |
| adaptive | small | 0.728 | 0.686 | 23 | 1.00 |
| adaptive | heavy | 0.484 | 0.430 | 33 | 1.00 |
| split:0.3 | small | 0.917 | 0.350 | 124 | 0.71 |
| split:0.3 | heavy | 0.851 | 0.220 | 328 | 1.00 |
| split:0.5 | small | 0.917 | 0.603 | 102 | 0.83 |
| split:0.5 | heavy | 0.801 | 0.290 | 220 | 1.00 |
| split:0.7 | small | 0.917 | 0.728 | 82 | 0.94 |
| split:0.7 | heavy | 0.710 | 0.332 | 130 | 1.00 |
| topk:10 | small | 0.894 | 0.603 | 57 | 0.98 |
| topk:10 | heavy | 0.835 | 0.309 | 206 | 1.00 |
| topk:5 | small | 1.000 | 0.603 | 116 | 0.87 |
| topk:5 | heavy | 0.872 | 0.154 | 348 | 1.00 |
| score:2.0 | small | 0.825 | 0.603 | 37 | 0.84 |
| score:2.0 | heavy | 0.451 | 0.451 | 33 | 1.00 |

**Recommended policy: `topk:10` (arm W2).** It best combines compressed-level
coverage with retained whole-file fidelity: heavy coverage 0.835 (near compressed's
0.896, well above adaptive's 0.484) while still delivering 0.309 of heavy
ground-truth files whole (vs topk:5's 0.154); on small, 0.894 coverage with 0.603
whole. `topk:5` pushes heavy coverage higher (0.872) but nearly halves whole
delivery; `split:0.5` is the conservative alternative (0.801 heavy coverage, 0.290
whole). Only the winning policy is taken to the agent run.

## Experiment (arm W2), pre-registered

Arm W2 is the Experiment 1 / Experiment 3 harness with `redcon_context` built from
the recommended tiered policy (`tiered_policy = "topk:10"`) through the same public
`run_pack` path, on the **held-out 24 tasks**, 2 repeats, equal size-scaled budget,
tool-less single call, forced unified diff, resumable and session-limit aware, with
records committed. Metrics are identical to Experiment 3 (file-overlap and
whitespace-tolerant line-overlap with parse-failure = 0, parse rate, per-arm input
via `cacheCreationInputTokens`, efficiency, cost, conditional-on-parse as the
exploratory secondary, and the whole-vs-compressed delivery fractions). No CLI
version drift is expected (2.1.220); if drift appears, follow the Experiment 3
control (re-run naive; do not re-run compressed unless a major version).

### Pre-registered hypotheses

- **H1:** W2 heavy file-overlap **> W adaptive (0.208)**. Recovering coverage while
  keeping the top files whole should raise heavy edit fidelity above plain
  adaptive.
- **H2:** W2 heavy pack-GT-coverage **>= 0.7**. A pack-level guardrail that the
  chosen policy actually restores coverage on the held-out heavy tasks (the dev
  sweep gives 0.835 for topk:10; H2 confirms it does not collapse off the dev set).
- **H3:** W2 small file-overlap **>= W adaptive (0.656) minus a noise margin of
  0.05**. Tiered rendering must not regress the small corpus, where plain adaptive
  already wins.

### Four-outcome interpretation (fixed before the run)

- **All three hold:** tiered rendering pays. Take `topk:10` forward as an
  adaptive-v2 candidate for the default, with the measurement cited, decided in a
  separate default-change PR (not automatic).
- **H1 fails:** restored coverage does not convert into heavy edit fidelity; tiered
  rendering does not pay. Adaptive stays as shipped, no default change.
- **H3 fails:** the policy helps heavy but regresses small. Not a uniform default;
  revisit a corpus-size-gated policy before any change.
- **Mixed / H2 fails:** exploratory only; no default change without a follow-up
  decision.

## Candidate second question: line-numbered whole files (needs a separate go)

A distinct lever, registered but **not** to be run without separate approval:
render whole files with line-number prefixes so the model can anchor exact `@@`
hunks (Exp 1/3 line-overlap is low even when file-overlap is high). This is a
second arm, so it is additional agent spend on top of W2 (roughly one more 48-cell
pass, order of the Exp 3 cost). It is not bundled into the W2 run; it gets its own
pre-registration and window if the reviewer chooses to pursue it.

## Guardrails

Same as Experiments 1 and 3: deterministic dev corpus and sweep, held-out eval set
never used for tuning, results and transcripts kept, backups between passes,
hypotheses and interpretation fixed before measurement. No agent runs until this
design is approved and a window is confirmed.

## Results (arm W2)

Run of record: 48 valid cells (held-out 24 tasks x 2 repeats, arm W2 = tiered
`topk:10`, CLI 2.1.220, no drift). $53.12 list-price. All numbers recompute from
`benchmarks/agentic/results/exp4-full/records.jsonl` (committed with this PR)
against the Experiment 3 `adaptive` and Experiment 1 `naive` / `redcon-compressed`
records. Metrics are identical to Experiment 3, plus per-task pack-GT-coverage and
the whole-vs-compressed delivery fractions.

| arm | corpus | file-ov | line-ov | parse | input (cc) | eff | cost | cond-parse fo/lo (n) | GT-cov |
|---|---|---|---|---|---|---|---|---|---|
| W2 tiered | small | 0.625 | 0.172 | 0.88 | 83k | 0.757 | $0.67 | 0.714 / 0.197 (21) | 0.875 |
| W2 tiered | heavy | 0.235 | 0.026 | 0.92 | 198k | 0.119 | $1.54 | 0.256 / 0.028 (22) | 0.756 |
| adaptive | small | 0.656 | 0.141 | 0.92 | 79k | 0.827 | $0.66 | 0.716 / 0.154 (22) | 0.750 |
| adaptive | heavy | 0.208 | 0.048 | 0.62 | 184k | 0.113 | $1.42 | 0.333 / 0.077 (15) | 0.363 |
| naive | heavy | 0.118 | 0.006 | 0.38 | 203k | 0.058 | $1.48 | 0.315 / 0.016 (9) | 0.130 |
| redcon-compressed | heavy | 0.122 | 0.020 | 0.54 | 197k | 0.062 | $1.51 | 0.225 / 0.036 (13) | 0.896 |

W2 delivered whole at fraction: small 0.348, heavy 0.121.

### Hypotheses against the pre-registered table

- **H1 (W2 heavy file-overlap > adaptive 0.208): HELD** - 0.235.
- **H2 (W2 heavy pack-GT-coverage >= 0.7): HELD** - 0.756 (recovered from adaptive's
  0.363, near compressed's 0.896, as designed).
- **H3 (W2 small file-overlap >= 0.606): HELD** - 0.625.

All three hold.

### Honest mechanism (the heavy win is parse-rate-driven)

The heavy gain over adaptive is real but modest (+0.027) and comes from parse rate,
not per-parse fidelity. W2 recovered coverage (0.756) and lifted the heavy parse
rate to 0.92 (vs adaptive 0.62), so the model commits to a valid diff far more
often. But conditional-on-parse, W2 heavy is lower (0.256 vs adaptive 0.333):
editing from a mostly-compressed context is less exact per file. Net,
0.92 x 0.256 = 0.235 beats 0.62 x 0.333 = 0.208. It is a trade, not a free win:
W2 heavy line-overlap drops (0.026 vs 0.048) because it delivers fewer files whole
(whole_frac 0.121 vs 0.430). On small, W2 file-overlap is marginally below adaptive
(0.625 vs 0.656, inside the H3 margin) while line-overlap is above (0.172 vs 0.141).
Pooled file-overlap is essentially tied (W2 0.430 vs adaptive 0.432): W2 shifts
fidelity from small toward heavy and from line-exactness toward parse and coverage.

### Paired per-cell (exploratory)

Same (sha, repeat) cell on file-overlap, W2 vs adaptive (win / loss / tie):
heavy **6 / 3 / 15**, small **1 / 2 / 21**. W2 wins more heavy cells than it loses
and is near-neutral on small.

### Size-gated composite (computed from measured cells, not a separate run)

The product decision is a size-gated adaptive-v2 (plain adaptive below the top
budget band, tiered `topk:10` in the >3M / 120k regime). Its expected one-shot
file-overlap on this corpus, formed by taking the measured **adaptive** small cells
and the measured **W2** heavy cells, is **pooled file-overlap 0.445** (vs plain
adaptive 0.432 and plain compressed 0.196). This is a composite of already-measured
cells, not a separate arm.
