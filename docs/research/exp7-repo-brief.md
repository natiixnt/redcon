# Experiment 7 design: task-independent repository brief

Status: **design and Phase A pre-registered. Phase A (the `redcon brief` command,
the django and sympy briefs, and this pre-registration) is deterministic and
free. No agent run (arm BR) until this design is approved and Natalia confirms a
window.**

## Motivation

Every delivery channel tried so far either failed or is narrow. Pull (the agent
calls redcon) failed on adoption; push (pre-inject a task-specific pack) failed in
the loop, and the P-lite variant (inject the ranking list) actively hurt: a
task-specific ranked file list **anchored** the agent and lowered recall. Adaptive
rendering (Exp 3) helped only one-shot flows. Tool-result compression (Exp 6)
closed as a negative ceiling.

The brief tests a different shape of context. Instead of task-specific pointers,
deliver a small, **task-independent** map of the repository: where modules live,
the entry points, the test layout, and the build and config conventions. The same
brief serves every task on the repo, so it cannot anchor a specific change the way
P-lite's per-task ranking did. The bet is that a cheap, stable orientation lowers
exploration cost without hurting recall or precision.

## Product artifact

`redcon brief` is a real command, not a bench-only tool.

- **Task-independent and deterministic.** It takes no task input and produces no
  per-change file ranking. It is built from scan, role, and import-graph
  aggregates: module geography (subpackages of the dominant package, or top-level
  directories, one line each with a short child descriptor), central modules (the
  most-depended-on production files by import-graph incoming degree, a structural
  property of the repo, not a task ranking), production entry points (conventional
  `__main__.py`/`manage.py`/`cli.py`/`wsgi.py`/... files at path depth <= 2, so a
  deeply nested `main.py` is not mistaken for a process entry point), test layout
  (where tests live, how many, and the `conftest.py` count), and root build and
  config files. Same tree in, same brief out; a determinism test pins this.
- **Capped.** The brief is trimmed to a hard token ceiling (default 2000, target
  1-2k) so it is cheap to keep in context; geography is dropped from the tail to
  fit and the result is marked truncated.
- **CI freshness.** `redcon brief --check PATH` regenerates the brief and exits
  nonzero when `PATH` is stale or missing, so a committed brief can be kept
  current in CI. `--out PATH` writes it; default prints to stdout; `--json` emits a
  structured report.

The brief deliberately contains **no ranked file list for any specific change**.
That is the P-lite trap; geography only.

Implementation: `redcon/brief.py` (`build_brief`), CLI `cmd_brief` in
`redcon/cli.py`, tests in `tests/test_brief.py`.

## Phase A (this PR): deterministic, no agent spend

1. The command, its determinism/token-cap/task-independence tests, and the
   `--check` CI mode.
2. Briefs for django and sympy at the 12 night-2 base commits (6 each), generated
   through the shipped `build_brief` path by `benchmarks/agentic/gen_exp7_briefs.py`
   and committed under `benchmarks/agentic/results/exp7-phaseA/`. The generator
   builds each brief twice and asserts byte-identical output. The clones
   themselves are not committed; the briefs and generator are.
3. This pre-registration.

Token counts and determinism for the 12 briefs are in the results table below for
review of quality, size, and stability across commits.

## Phase B design (pre-registered, not run)

### Arm BR

Arm BR is the night-2 heavy harness, changed in exactly one place: the repository
brief for the task's base commit is appended to `CLAUDE.md` in the worktree before
the agent starts. Headless Claude Code reads `CLAUDE.md` but not `AGENTS.md` (the
1.16 delivery lesson), so the brief actually reaches the model. Everything else is
held to the night-2 baseline: 12 heavy tasks (django and sympy) x 3 precise
repeats = **36 runs**, about the night-2 baseline arm cost.

### Baseline

Reuse the night-2 baseline arm (B) if the Claude Code CLI is still 2.1.220 at run
time. If the CLI has drifted, add **6 fresh B control runs** alongside BR per the
standing drift rule, so the comparison is against a contemporaneous baseline.

### Hypotheses

- **H1 (cost).** BR cost per run <= baseline. The brief is tiny and re-read
  cheaply from cache, and a correct orientation should cut exploration turns.
- **H2 (recall).** BR file recall >= baseline. Task-independent geography must not
  hurt what the agent finds.
- **H3 (precision).** BR precision does not collapse. The brief names no task
  files, so no P-lite-style anchoring is expected.

### Mechanism metrics

Turns, time-to-first-edit, and the redcon-brief token share of total input, to
show *how* any cost or recall change arises (fewer exploration turns, faster first
edit) rather than only *that* it does.

### Four-outcome interpretation (pre-registered)

| observation | reading | action |
|---|---|---|
| cost down at recall parity, or recall up at cost parity | the brief pays | promote `redcon brief` as a shipped feature with CI freshness (`--check`) |
| cost up, or recall down | honest null | the feature stays optional, not promoted |
| precision collapse | the anchoring mechanism reaches even task-independent context | record prominently: geography alone anchors, a strong negative result |

## Gating

Design, briefs, and this pre-registration come to Natalia for review **before any
run**. Phase B (arm BR) fires only on a confirmed window. No hypotheses or
interpretations are added after the run.

## Results (Phase A): the 12 briefs

Token counts and determinism, from `benchmarks/agentic/results/exp7-phaseA/index.json`:

| repo | base commit | files | brief tokens | packages summarized |
|---|---|---:|---:|---|
| django | `36be97b99d4d` | 5635 | 556 | no |
| django | `21c51c2623a9` | 5653 | 556 | no |
| django | `56050acb96ab` | 5680 | 556 | no |
| django | `673fa46d8063` | 5646 | 556 | no |
| django | `e7f539f813bd` | 5653 | 556 | no |
| django | `f2169ef36884` | 5638 | 556 | no |
| sympy | `1e925fca57b6` | 2049 | 775 | yes |
| sympy | `af838d955f42` | 2053 | 776 | yes |
| sympy | `cbd5424918c3` | 2054 | 776 | yes |
| sympy | `d3f6039f88b2` | 2063 | 776 | yes |
| sympy | `afb25b0d7db1` | 2052 | 776 | yes |
| sympy | `f9a6c6dda7c2` | 2052 | 776 | yes |

All 12 briefs render byte-identically on a repeat build (the generator asserts
it). Every brief is far under the 2000-token ceiling: django is 556 tokens across
all six commits, sympy 775 to 776. The token count is near-constant across a
repo's commits, which is the task independence and stability the design intends.

The sympy "packages summarized" column is yes because sympy has more subpackages
(40) than the geography section lists individually (the 24 largest), with the rest
folded into a "... and N more subpackages" line. That is the readability cap on the
package list, not token-ceiling trimming: no brief here was trimmed to fit the
token budget. django has fewer than 24 subpackages, so every one is listed.

The briefs surface each repo's genuine core in the Central modules section (for
django, `db/__init__.py` imported by 778 modules, `db/models/__init__.py` by 643,
`core/exceptions.py` by 356; for sympy, its core and utilities packages), and the
entry-point depth guard keeps out deep `main.py` files (the earlier
`django/contrib/admin/views/main.py` false positive is gone), so django's only
entry point is `django/__main__.py`.
