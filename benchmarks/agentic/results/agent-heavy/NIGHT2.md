# Agent arm, night 2: context-heavy corpus (pre-registration)

This file is committed before the run: the hypotheses below are registered up
front, and the results are filled in afterwards under each one.

Night 1 found no end-task benefit from redcon on small repositories and traced
the one clear loss to a behavioural cause - the agent never called redcon's
tools and grepped by hand instead. Night 2 separates the two questions night 1
conflated: does the pack help when it is used, and how often does the agent use
it unprompted.

## Design

- Corpus: `benchmarks/agentic/tasks-heavy.jsonl` - 12 tasks from django and
  sympy (large repos, several million tokens each), touching 3-8 files across
  >= 2 directories, 60-400 line diffs, stratified 4 small / 4 medium / 4 large.
- Three arms:
  - **A** (`redcon`): redcon MCP available, prompt identical to baseline.
  - **Ag** (`redcon_guided`): redcon MCP available, prompt plus one neutral line
    ("This repository has redcon MCP tools available; calling redcon_rank or
    redcon_budget first is usually cheaper than searching manually.").
  - **B** (`baseline`): no MCP at all.
- Decomposition: **pack value = Ag vs B**; **cost of non-adoption = A vs Ag**.
- Model sonnet, `--max-turns 30`, window-aware and resumable. Every run is
  captured as a stream-json transcript (kept under `transcripts/`), and the
  per-run count of `mcp__redcon__*` calls is recorded as a first-class metric -
  without it adoption and value cannot be told apart.
- Passes: pass 1 = 12 x {A, B} x 3 (precise); pass 2 = 12 x Ag x 3 (precise) plus
  a medium addendum 12 x {Ag, B} x 1.

## Pre-registered hypotheses

1. **Pack value.** On these large repos, Ag beats B on cost at equal or better
   recall.
2. **Cost of non-adoption.** A minus Ag is non-trivial and is explained by redcon
   tool-call counts (A calls the tools rarely, Ag often). This is a
   tool-description problem, not a pack-value problem.
3. **Wording sensitivity.** Ag's advantage over B grows from precise to medium.

## Caveat, registered up front

Medium differs from precise for only 8 of the 12 tasks - 4 sympy subjects name no
file or symbol, so their medium collapses onto precise. The precise-vs-medium
comparison (hypothesis 3) is therefore reported on that distinguishable subset,
with the count stated, so the medium addendum is not read as more than it is.

## Pass 1 results (arms A and B, precise, 72 runs, one window)

Zero adoption. Arm A called a redcon tool 0 times across all 36 runs, on repos of
several million tokens. "Available but unprompted" is pure schema overhead with no
use, and A comes out slightly behind B.

| arm | cost/run | turns | recall | precision | capped | redcon calls |
|---|---|---|---|---|---|---|
| A (redcon) | $0.82 | 23.2 | 0.62 | 0.82 | 16/36 | 0 |
| B (baseline) | $0.78 | 19.8 | 0.69 | 0.80 | 10/36 | 0 |

The night-1 audit (the agent greps by hand instead of ranking) is confirmed at
full scale. This makes pass 2 the decisive test: whether one guidance line moves
adoption off zero, and if so whether the pack then pays.

## Pre-registered interpretation of pass 2 (recorded before pass 2 ran)

Fixed in advance so no narrative is fitted after the fact:

- **Ag adopts and beats B** (cost down at equal-or-better recall): thesis
  conditionally confirmed - the pack works when the agent uses it. Action for
  1.16: ship guidance by default (installer writes a client rule) and slim the
  tool schemas.
- **Ag adopts but does not beat B**: pack value on this terrain is refuted. Then a
  serious repositioning conversation - token savings in API/CI workflows and cache
  stability, not "better interactive-agent outcomes".
- **Ag does not adopt**: one prompt line is not enough; the next measured step is a
  client config-file rule (CLAUDE.md-style), which is exactly what the installer
  can write.
- **Mixed by stratum**: an applicability-boundary map for the writeup.

Independent of the outcome, one finding is already hard and goes to 1.16: adoption
is a first-class product problem. A tool the agent does not call does not exist,
however good the pack.

### Ag and Agc are two channels, not two doses

If a pass 3 runs (arm Agc), do not read Ag vs Agc as "less text vs more text". They
answer two different questions, and both matter:

- **Ag** measures the **minimal intervention**: a single neutral line in the prompt.
- **Agc** measures the **shipped product**: redcon's installer block written to the
  client rules file the CLI reads automatically.

So if Agc drives adoption where Ag does not, the conclusion is not "more guidance
helps" - it is "the client-config channel works, the prompt channel does not."
That is directly actionable for 1.16: ship the config-file rule (the installer
already writes it), and do not rely on prompt-level hints. The content difference
between the two arms is a property of each channel as it actually ships, not a
confound to explain away.

## Arm P (pre-injection) - registered before its run

Every MCP arm is bottlenecked on adoption, so none of them can measure the pack's
value while adoption sits at zero. Arm P removes adoption from the equation: the
agent's prompt is prefixed with a redcon pack generated up front (precise phrasing,
30k budget, the pack report pasted before the task), and the agent then works with
its normal file tools and no MCP. 12 tasks x 3 repeats precise = 36 runs, compared
against the existing B data.

**Hypothesis (registered before the run):** pre-injection bypasses adoption
entirely, so P measures the pack's pure value. P should beat B on cost and turns at
equal-or-better recall, because the agent starts from a map instead of grepping for
one. If P does not beat B, the pack's value on this terrain is refuted independently
of adoption - a stronger negative than the MCP arms could give.

## Causal-chain protocol for the Ag transcripts

Adoption plus a win is only a correlation; the transcripts turn it into a chain.
For every Ag run, read from the stream-json transcript and report per run: which
redcon tools were called and at which turn, the file set redcon_rank/redcon_budget
returned, and the overlap of files_edited with that set - i.e. did the agent edit
the files the pack pointed at, and did cost fall as a result.

## Threats to validity (scope of the adoption result)

The adoption finding is measured in **headless, autonomous mode** (`claude -p`)
with **model sonnet**. It says nothing about an interactive user who can tell the
agent "use redcon" directly, and other models may have different tool-use habits.
The claim is "the autonomous sonnet agent does not reach for redcon on its own
here", not "agents never use redcon".

## Pre-registered product thesis (recorded before arm P ran)

Written before seeing P, to be honest with ourselves:

- If adoption is zero across every pull channel (no guidance, prompt line,
  config-file rule) **and P shows value**, the conclusion is **value delivers by
  push, not pull**: a pack injected before the agent starts (hooks, a pack-first
  CLI, CI, the gateway) works, while "install the MCP server and the agent will
  reach for it" is not a real delivery path today. That shifts the 1.16 priority
  from "better tool descriptions" to "auto-injection as the flagship integration".
- If **P does not show value**, the pack's worth on this terrain is refuted even
  with adoption removed, and we return to the positioning conversation with harder
  data. The `pack_file_hits` metric guards this branch: a P loss only counts
  against the pack if the pack actually contained the ground-truth files.

## Arm P120 (pre-injection at 120k) - registered before its run

The sweep shows a 120k pack reaches ~0.90 coverage, so P120 tests pre-injection
with a near-complete map: 12 tasks x 2 repeats precise = 24 runs, pack-file-hits
recorded.

**Hypothesis (registered before the run):** at ~0.9 coverage P120 improves recall
over B, but cost may not fall in a long loop, because the 120k map is re-read every
turn. The result decides whether push pays in interactive loops too or only in
short flows. **Technical caveat, also registered:** a 120k prefix plus a growing
conversation may approach the model's context window; if runs are truncated, that
is itself a finding - a full-coverage map does not fit in an interactive loop - and
is reported as such rather than discarded.

## Coverage sweep (budget diagnostic, deterministic, no agent cost)

Pre-injection carried only 64% of the ground-truth files at the 30k default, and
the heavy corpus has no layer-1 data, so this sweep runs the layer-1 pack over
tasks-heavy at four budgets to tell a budget limit from a ranking limit
(`coverage_sweep.py`, `coverage_sweep.json`):

| budget | pack file-hits |
|---|---|
| 12k | 0.358 |
| 30k | 0.627 |
| 60k | 0.738 |
| 120k | 0.896 |

Coverage climbs steadily toward ~1.0, so **this is a budget limit, not a ranking
limit**: redcon's ranking surfaces the right files on django/sympy given enough
tokens, and 30k is simply too small for multi-million-token repos. The 30k pack
in arm P was therefore an incomplete map by construction.

## Results (204 runs: A, B, Ag precise; Ag, B medium; Agc, P precise)

### All arms, precise (n=36 each)

| arm | cost/run | turns | recall | precision | capped | adopted |
|---|---|---|---|---|---|---|
| B baseline | $0.78 | 19.8 | 0.688 | 0.799 | 10 | 0/36 |
| A redcon | $0.82 | 23.2 | 0.618 | 0.822 | 16 | 0/36 |
| Ag guided | $0.91 | 25.7 | 0.617 | 0.814 | 19 | 0/36 |
| Agc config | $0.69 | 20.8 | 0.588 | 0.676 | 12 | 4/36 |
| P preinject | $1.84 | 22.2 | 0.634 | 0.412 | 15 | 0/36 |

Per-stratum recall (precise, n=12/cell):

| stratum | B | A | Ag | Agc | P |
|---|---|---|---|---|---|
| small | 0.611 | 0.535 | 0.486 | 0.375 | 0.549 |
| medium | 0.623 | 0.595 | 0.683 | 0.675 | 0.536 |
| large | 0.830 | 0.723 | 0.682 | 0.714 | 0.817 |

### Hypothesis outcomes

- **H1 (pack value, Ag vs B): not supported.** Ag did not beat B - it cost more
  ($0.91 vs $0.78) at lower recall (0.617 vs 0.688), because adoption was zero.
  The clean value test is arm P, below.
- **H2 (cost of non-adoption, A vs Ag): supported and then some.** Carrying redcon
  unused cost more than baseline (A $0.82 vs B $0.78); adding the guidance line made
  it worse still (Ag $0.91, 25.7 turns, 19/36 capped). Adoption stayed at zero.
- **H3 (wording, precise vs medium): not supported.** On the distinguishable
  subset (8/12 tasks; the 4 sympy subjects collapse medium onto precise), Ag medium
  recall 0.635 vs B 0.543 is within noise and adoption was zero in both, so there
  is no pack effect for wording to modulate.

### Adoption

Zero through the prompt channel (A 0/36, Ag 0/36). The **CLAUDE.md config channel
(Agc) is the only one with any adoption at all: 4/36** - and only `redcon_rank`,
only on sympy. (Headless Claude Code reads CLAUDE.md, not AGENTS.md; redcon's
installer writes only AGENTS.md, so its shipped guidance never reaches this agent -
a 1.16 delivery bug.)

### Cost decomposition (mean tokens/run, precise)

| arm | cache-read | cache-write | output |
|---|---|---|---|
| B | 1.31M | 42k | 9.2k |
| Ag | 1.55M | 44k | 11.8k |
| P | 2.78M | 127k | 10.8k |

**P's 2.4x cost is the injected map, and it scales with turns:** the 30k pack is
cache-written once (~3x baseline) and re-read every turn (2.78M, ~2x). So
pre-injection pays most in **one- and few-turn flows** (CI, batch jobs, review
bots, single API calls) and least in long interactive loops - which narrows the
flagship auto-injection use case in 1.16 to automated modes.

### Ag: unheard guidance is worse than no guidance

Ag was the single worst arm. Versus A, its extra turns went to *more* manual
search - Read 6.4 vs 4.7, plus ToolSearch 0.9 - the agent hunted around after
being told about tools it never called, inflating turns (25.7) and cap-outs
(19/36) with no offsetting use.

### Agc: causal chain, and context has value at the start

The 4 adopters each called `redcon_rank` once (20 files ranked). Timing decided
value: the two early calls (turns 6-7, both sympy/afb25b0d7 and sympy/d3f6039f8)
reached recall 1.0; the two late calls (turns 27 and 33, after the agent had
already grepped) landed recall 0.0. **Ranking is only useful before the agent has
built its own map** - context has value at the start of a run, not mid-run.

### P: pack value once adoption is removed

P did not beat B: cost 2.4x, recall 0.634 vs 0.688, and **precision collapsed to
0.412** (vs 0.799). Mechanism, from the transcripts: the agent anchors on the
injected map and edits files it lists that are not targets - e.g. django/36be97b9
rep0 edited 8 files, 5 of them non-targets, one taken straight from the pack
(`tests/staticfiles_tests/.../ignored.css`). Averaged 3.3 superfluous edits/run.

P's recall tracks the pack's coverage almost exactly (0.634 vs pack-file-hits
0.627): the agent trusts the map, so an incomplete map caps recall below what free
grep achieves (0.688).

**Exploratory, post-hoc, small n (not a confirmed result):** on the 6 runs where
the injected pack happened to be complete (pack-file-hits = 1.0), P recall was
0.78 - above baseline's 0.69. This is consistent with the hypothesis "fix coverage
(a budget fix, per the sweep) and push may pay", but n=6 and it is not a
pre-registered comparison; treat it as a lead, not a finding.

### The "inject before start" thesis

Three independent pieces of evidence converge: (1) Ag spent its extra turns
searching instead of ranking; (2) Agc's `redcon_rank` helped only when it came
early, not late; (3) P did best exactly on the tasks where the up-front map was
complete. The pack's value lands when it is present at the start of the run, which
is the push (pre-injection) mode, not the pull (call-a-tool-mid-run) mode.

## Bottom line

On large repositories, redcon faces **two distinct problems**, both measured:

1. **Delivery / adoption.** The autonomous sonnet agent will not reach for redcon
   on its own: 0/36 unprompted, 0/36 with a prompt line, 4/36 via the CLAUDE.md
   rule. Guidance alone does not move it.
2. **Budget-bounded coverage.** At the 30k default the pack covers only 64% of the
   changed files on django/sympy (a budget limit - it reaches 0.90 at 120k), and
   pre-injecting an incomplete map is measured harm (precision 0.41, recall below
   baseline).

Value is delivered by **push, not pull** - but push only pays once the budget/
coverage gap is closed and in automated, short-turn flows where re-reading the map
is cheap. This reprioritizes 1.16 toward budget-scaled packing and auto-injection
in CI/batch modes rather than tool-description tweaks; the full backlog is in the
1.16 notes. The layer-1 results (97.8% file recall, contexts 63-93% smaller) stand
for small and medium repositories; these limits are specific to multi-million-token
repos in headless autonomous mode with sonnet.
