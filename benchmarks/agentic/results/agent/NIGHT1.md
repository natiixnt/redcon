# Agent arm, night 1: small-repo pilot

Layer-2 pilot of the agent-in-the-loop arm (`agent_arm.py`). Each task is run by
the Claude Code CLI headless, once with the redcon MCP server available (arm
`redcon`) and once with no MCP at all (arm `baseline`); the prompt is identical
across arms, so the only difference is the tool surface.

## Pre-registered hypothesis and result

**Hypothesis (registered in the harness header before the run):** an MCP server
adds a roughly fixed per-session cost (its tool schemas sit in the cached
context whether or not they are called), so redcon is expected to be ~neutral on
small, well-localized tasks and to gain on context-heavy tasks.

**Result:** no measured end-task benefit on small repos. On this corpus redcon
is neutral-to-slightly-behind the baseline, and the corpus does not create the
context-pressure regime the tool targets, so this night does not test the part
of the hypothesis where redcon is expected to win. See night 2 for the
context-heavy regime.

## Setup

- Tasks: the pinned 12 in `benchmarks/agentic/pilot-tasks.txt` (4 small / 4
  medium / 4 large by global diff-size tercile, 4 per repo across redcon, httpx,
  click), phrasing `precise`.
- Arms: `redcon` (redcon MCP) and `baseline` (empty strict MCP config).
- 3 repeats per task/arm (repetition for variance, not RNG seeds). Model sonnet,
  `--max-turns 30`.
- 72 runs, 0 errors, completed in a single usage window (~124 min wall). Total
  list-price cost (a reported metric, not an API charge): $48.41.

Metrics: **recall** = fraction of the commit's changed files the agent edited;
**precision** = fraction of the agent's edits that were changed files (post-hoc
from `files_edited` vs `changed_files`); **cost** = CLI list-price USD;
**capped** = runs that hit the 30-turn ceiling.

## Overall (n = 36 per arm)

| arm | cost/run | turns | recall | precision | capped |
|---|---|---|---|---|---|
| redcon | $0.66 | 17.2 | 0.61 | 0.49 | 12/36 |
| baseline | $0.68 | 17.4 | 0.69 | 0.58 | 9/36 |

At parity cost and turns, the baseline slightly leads on both recall and
precision.

## By stratum (n = 12 per cell)

| stratum | arm | cost | recall | precision | capped |
|---|---|---|---|---|---|
| small | redcon | $0.45 | 0.50 | 0.50 | 3 |
| small | baseline | $0.51 | 0.50 | 0.50 | 3 |
| medium | redcon | $0.57 | 0.88 | 0.64 | 3 |
| medium | baseline | $0.79 | 0.90 | 0.77 | 3 |
| large | redcon | $0.97 | 0.46 | 0.33 | 6 |
| large | baseline | $0.75 | 0.67 | 0.47 | 3 |

Small is a wash (redcon marginally cheaper). Medium is the one place redcon is
clearly cheaper (~28%), but at a precision cost. Large looks like a redcon
regression - but see below.

## The large-stratum gap is one task, not a trend

With four tasks per stratum, one task swings the cell. Per-task recall on the
four large tasks (redcon vs baseline, mean over 3 repeats):

| task | redcon | baseline | note |
|---|---|---|---|
| click/18400b2 | 1.00 | 1.00 | wash |
| httpx/2318fd8 | 0.67 | 0.67 | wash (both missed the source files) |
| redcon/4386504 | 0.00 | 0.00 | both fail, both cap out (hard task) |
| redcon/56c7b8d | 0.17 | 1.00 | redcon arm fails, baseline succeeds |

The entire large-stratum gap comes from one redcon-repo task (56c7b8d). Drop it
and large is a wash too. This is not evidence that redcon hurts on large changes;
it is one task worth understanding, audited below.

## Audit: why the redcon arm failed on 56c7b8d

The task, "Fix first-run correctness bugs: python -m, scan-index scoping, atomic
cache, git quoting", touches four files across four subsystems
(`redcon/cache/backends.py`, `redcon/cli.py`, `redcon/scanners/incremental.py`,
`redcon/stages/workflow.py`) - a multi-locus change.

The pilot only kept each run's final JSON (the failed runs had empty summaries),
so the failure was reproduced once with the CLI transcript captured
(`--output-format stream-json`). The reproduction matched the pilot outcome: 31
turns, capped, error, no correct edit landed.

What the transcript shows:

- **The agent never called a redcon tool.** Tool usage across the run was Bash
  x17, Read x8, Edit x4, Write x1, redcon MCP **x0** (a first partial capture
  showed the same pattern: Bash x25, Read x10, redcon x0). Redcon's schemas sat
  in the context the whole time and were never used.
- **The turns went to manual search.** The 17 Bash calls are `grep`/`find`
  sweeps locating each of the four loci by hand ("python -m", "scan-index",
  "shlex/quote", "atomic/cache"). The agent burned its budget rediscovering the
  file set before it could finish editing.
- **Ranking was not the problem.** Layer 1 for this same sha shows redcon's pack
  surfacing all four changed files (file_hits 1.0 at 30k/60k, 0.75 at 12k). One
  `redcon_rank` call would have replaced the whole grep phase.

So the failure is **behavioral, not a ranking or wiring failure**: the tools
were present and would have helped, but the agent defaulted to Bash-grep and the
tool descriptions were not compelling enough to pull it off that path. The fixed
per-session schema cost bought nothing because the tools were not called.

Product implications (recorded for 1.16, no product change before night 2 so the
tested version stays fixed): the schema overhead is dead weight unless the agent
actually reaches for the tools, which argues for both **slimming the tool
descriptions** and **strengthening the "call redcon_rank first" guidance** so the
agent prefers a single ranked lookup over a grep sweep. To be re-measured after
night 2.

Caveat: one task, reproduced once (plus one partial); the pattern is consistent
across both captures and explains the pilot outcome, but n is tiny.

## Bottom line

On small repositories with small, localized commits, redcon delivers no measured
end-task benefit and is neutral-to-slightly-behind at equal cost. That is a real
result, but it is a result about terrain the tool is not built for: these repos
never put the context under pressure. Night 2 runs the same protocol on a
context-heavy corpus (large multi-file commits in large repositories) to test
the half of the hypothesis this night could not.
