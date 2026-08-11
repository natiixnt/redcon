# Experiment 2 design: P-lite (inject the ranking, not the map)

Status: **design only, pre-registered. No runs until this design is approved and
Natalia confirms a usage window.**

## Motivation

Night 2 injected the full pack (arm P at 30k, P120 at 120k) and both lost to
baseline in a multi-turn loop: the large map is re-read every turn (2.4-3.5x
cost), recall does not improve, and at 120k a third of runs cap out. (Precision
was originally reported as collapsing to ~0.41; that was a `.redcon` artifact in
`files_edited` - see the correction note under Results. Precision is intact.) Yet
two signals point the other way: Agc's `redcon_rank`
helped when it came early, and context has value at the start of a run. P-lite
tests the minimal version of that: give the agent only the **ranking list**, not
the content, and let it read the files itself.

## Design

Inject at the start of the prompt a short list - the top ranked file paths plus a
one-line note on why (role or match) - then run the agent normally with its file
tools and no MCP. The agent still reads whatever it needs; it just starts from the
right files instead of grepping for them.

### List size, pinned

**K = 10** ranked files; each entry is a path plus a one-sentence role. Ten entries
at roughly a path (~40 chars) plus a short role (~60 chars) is about 1,000
characters, i.e. **~250 tokens - comfortably under the ~500-token cap**. The cap is
asserted at build time so an over-long list fails fast rather than quietly turning
P-lite into a small pack.

### Drift control against the reused baseline

P-lite reuses the night-2 baseline B (run with CLI 2.1.220, model claude-sonnet-5)
rather than re-running it. To guard against silent drift, each new P-lite run
records the CLI and model version. If either differs from the night-2 baseline, add
**6 fresh B control runs** on the same tasks under the new versions and report both
baseline lines (reused and fresh) so any shift is visible, not absorbed.

- **Arms:** P-lite vs the **existing** baseline B (reuse the night-2 B records; no
  new baseline runs needed).
- **Corpus:** `tasks-heavy.jsonl` (django, sympy).
- **Scale:** 12 tasks x 2 repeats precise = 24 runs.
- **Metrics:** cost, turns, recall (file-hits), precision, cap-out rate, and the
  ranking's own coverage of the ground-truth files (as `pack_file_hits` was for P).

## Pre-registered hypothesis

Because the injected list is tiny (~500 tokens, re-read cheaply) and the agent
still reads files itself, P-lite should:

1. cost **~= baseline** (no large map to re-read),
2. recall **above baseline** (it starts from the right files), and
3. **not** collapse precision the way P and P120 did (it is not anchored on a full
   map of files to edit, only pointed at where to look).

If P-lite matches this, it is the cheap, in-loop delivery that the full-map push
arms failed to be, and a candidate for a redcon "start-here" hint. If it does not
beat baseline, the start-from-the-right-files idea does not survive contact with
the loop even at minimal cost, and push is closed for interactive use.

## Relation to the other open branches

Complementary to experiment 1 (one-shot selection quality). Exp 1 asks whether the
selection is good; P-lite asks whether a minimal in-loop delivery of that selection
pays where the full map did not. Together they bound where redcon's measured
selection quality can and cannot be turned into end-task value.

## Cost estimate

24 runs at roughly baseline per-run cost (the injected list is small), so on the
order of the night-2 baseline arm - low tens of dollars list-price. A precise
estimate and a 2-run calibration accompany the run request. No runs until approved
and a window is confirmed.

## Results

P-lite full run: 24 valid runs (12 heavy tasks x 2 precise repeats), $15.93
list-price, compared against the reused night-2 baseline B (arm `baseline`,
precise). All numbers recompute from
`benchmarks/agentic/results/plite-full/records.jsonl`, committed with this PR;
full stream-json transcripts are archived at
`~/redcon-exp-backups/exp2-plite-transcripts.tar.gz` (1.3M).

Correction note (dated 2026-08-11): the precision figures first reported here
(P-lite 0.465, baseline 0.881) were a harness artifact and are wrong. The pack
build ran redcon inside the worktree, so `.redcon/`, `.redcon_cache.json` and its
lock landed in `files_edited` for every P-lite run (24/24) while baseline had none
(0/36), deflating P-lite precision. Recomputed with `.redcon*` paths excluded on
both arms, the numbers below are correct and **H3 is held, not refuted.**

| metric | baseline B | P-lite | pre-registered hypothesis |
|---|---|---|---|
| cost | $0.776 | $0.664 | H1 (cost ~= baseline): **held** (slightly cheaper) |
| turns | 19.8 | 17.8 | - |
| recall (file_hits) | 0.688 | 0.556 | H2 (recall > baseline): **refuted** |
| precision (`.redcon` excluded) | 0.872 (33 runs) | 0.943 (18 runs) | H3 (no precision collapse): **held** |
| cap-out | 11/36 (31%) | 8/24 (33%) | - |
| ranking coverage of GT | - | 0.270 | - |

**Verdict: negative on H2, but H3 holds.** P-lite matches baseline on cost, does
not beat it on recall, and does **not** collapse precision - its precision (0.943)
is in fact slightly above baseline (0.872).

**Mechanism (corrected).** The ranking did **not** anchor edits onto wrong files:
precision is intact. What it did was **narrow exploration** - P-lite took fewer
turns (17.8 vs 19.8) and reached fewer ground-truth files (recall 0.556 vs 0.688).
Pointed at a top-10 list that covered only 27% of the ground-truth files
(`ranking_file_hits` = 0.270), the agent searched less and stopped short, rather
than editing the wrong things. Push delivery stays closed for interactive use, but
on **cost and recall** grounds, not precision: P costs 2.4x at recall 0.634, P120
3.4x with a 33% cap-out rate, and P-lite trades recall for a shorter loop with no
offsetting benefit.

**Metric definitions.** recall = `file_hits` (fraction of ground-truth files the
agent edited); precision = |files_edited and changed_files| / |files_edited|,
computed post-hoc over runs that edited at least one file; cap-out = runs whose
`terminal_reason` is not `completed`. **`files_edited` excludes any path starting
with `.redcon`** (redcon's own cache artifacts, written by the pack build, are not
agent edits). The run filter is harness-error only (runs with an `error` key are
dropped; CLI `is_error` runs are kept, matching the night-2 baseline slice).

**Caveats.** P-lite n = 24 vs baseline n = 36 (2 vs 3 repeats). Precision is
averaged over runs that edited at least one non-artifact file: 18 of 24 P-lite runs,
33 of 36 baseline runs. (An earlier draft reported 16 P-lite editing runs; that
count came from an erroneous extra `is_error` filter that dropped 8 runs - the
correct filter keeps all 24, of which 18 edited a real file.) Baseline B is reused
from night 2 with no version drift (both under CLI 2.1.220, model claude-sonnet-5),
so no fresh baseline controls were required.
