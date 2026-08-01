# Roadmap: Self-contained progressive packer

Goal: every prompt Redcon produces is complete and useful on its own, and the
packer maximizes information density under any budget by degrading
representations before dropping files entirely.

Status: the three phases below shipped in March 2026. This document records
what was delivered, with commit and test references, plus the small follow-ups
that remain open. It is not a list of pending work.

---

## Phase 1 - Self-contained cache (P0) - Done

Delivered in `3ad9611` (self-contained cache) and `3b92412` (removed the dead
code path that emitted `@cached-summary:` markers).

- On a cache hit the compressor keeps the real compressed text in
  `CompressedFile.text`; the hit only skips a redundant `put_fragment`. The
  reference id lives in `cache_reference` for accounting and never touches
  `text` (`redcon/compressors/context_compressor.py`, `_finalize_entry`).
- `redcon/runtime/runtime.py` guards `_build_prompt_text`: any entry whose text
  starts with `@cached-summary:` is logged and skipped. `redcon/cli.py` carries
  the same guard on its render paths. The marker is never constructed anywhere
  in `redcon/`; it exists only as guarded input and one deliberately broken
  test fixture.
- Tests: `test_warm_cache_produces_self_contained_prompt` and
  `test_runtime_build_prompt_skips_cache_markers` in
  `tests/test_pack_pipeline.py`.

---

## Phase 2 - Progressive budget packer - Done

Delivered in `3ad9611`.

- `redcon/compressors/representations.py` builds a per-file tier list
  (`full`, `symbol`, `slice`, `summary`) of decreasing token cost.
- `compress_ranked_files()` runs a tentative pass (best affordable
  representation per file, in score order) followed by a bounded degradation
  pass that downgrades the lowest-scoring included files to reclaim budget for
  otherwise-skipped files. Controlled by `progressive_packer_enabled` and
  `max_degradation_rounds` in `[compression]` (`redcon/config.py`).
- `CompressionResult` carries `degraded_files` and `degradation_savings`, and
  the quality-risk estimate accounts for the degraded ratio.
- Tests: `test_progressive_packer_degrades_before_dropping`,
  `test_progressive_packer_triggers_degradation_with_metrics`,
  `test_progressive_packer_no_degradation_with_large_budget`,
  `test_greedy_fallback_when_progressive_disabled`,
  `test_pack_never_exceeds_budget_under_degradation`.

---

## Phase 3 - File-role priors - Done (two minor follow-ups open)

Delivered in `04571b4`, `02d31bd`, and `840574e`.

- `redcon/scorers/file_roles.py` classifies each scanned file into `prod`,
  `test`, `docs`, `example`, `config`, or `generated` via path heuristics.
- `redcon/scorers/relevance.py` applies `role_multipliers` after heuristic
  scoring, with `role_keyword_overrides` for the test/docs/example special
  cases. Both live in `[score]` (`redcon/config.py`) and are config-validated.
- Tests: `test_file_role_classification_basic`,
  `test_file_role_does_not_match_substrings`,
  `test_role_multipliers_lower_docs_and_examples`,
  `test_role_keyword_override_boosts_test_files`.

Open follow-ups (minor, not blocking):

1. The computed role is not stored on `RankedFile`, so it is not visible to
   downstream consumers or `run.json`.
2. The role is recomputed on every score run rather than cached in the scan
   index. `840574e` added an `lru_cache` to `classify_file_role`, which removes
   most of the repeated cost, so this is an optimization rather than a
   correctness gap.

---

## What is next

The progressive-packer arc above is complete. Current direction is tracked in
the launch backlog and issues, not in this document. The near-term 1.12.0 work
is the free max-compression profile, changed-file targeting for `plan` and
`pack`, and a per-file scoring breakdown in `plan` output and `run.json`.
