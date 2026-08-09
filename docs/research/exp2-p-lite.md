# Experiment 2 design: P-lite (inject the ranking, not the map)

Status: **design only, pre-registered. No runs until this design is approved and
Natalia confirms a usage window.**

## Motivation

Night 2 injected the full pack (arm P at 30k, P120 at 120k) and both lost to
baseline in a multi-turn loop: the large map is re-read every turn (2.4-3.5x
cost), the agent anchors on it (precision collapses to ~0.41), and at 120k a
third of runs cap out. Yet two signals point the other way: Agc's `redcon_rank`
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
