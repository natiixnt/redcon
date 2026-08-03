# Redcon Launch Backlog (20 Issues)

This backlog is aligned with the current repository (CLI + Python API + examples + CI policy + telemetry abstraction) and near-term roadmap items.

Statuses were audited against the shipped code (through 1.13.0). Each issue
carries a **Status** line: `Delivered`, `Partial`, or `Open`. Entries are kept
in place for provenance; nothing is removed when an item ships.

## Issues

1. **Publish JSON Schemas for `run.json`, diff, and benchmark artifacts**
   - Add versioned schema files for run, diff, and benchmark outputs.
   - Add schema validation tests to protect contract stability for integrations.
   - Labels: `core`, `artifacts`, `api`.
   - **Status:** Delivered - versioned draft 2020-12 schemas under `redcon/schemas/json/v1/` with validation tests (1.13.0).

2. **Add `redcon validate <artifact.json>` command**
   - Validate artifacts against JSON Schemas.
   - Return non-zero on invalid schema in CI.
   - Labels: `cli`, `artifacts`, `ci`.
   - **Status:** Delivered - `redcon validate` picks the schema by `command`, exits 0/1, `--json` errors (1.13.0).

3. **Add changed-files targeting for `plan` and `pack`**
   - Accept changed-file paths as optional input.
   - Prioritize changed files and nearby dependencies in ranking.
   - Labels: `cli`, `scoring`, `workflow`.
   - **Status:** Delivered - `--changed` boosts named files and one-hop import neighbours (1.12.0).

4. **Generate shell completions for bash and zsh**
   - Add completion scripts and install instructions.
   - Keep command/help output compatibility.
   - Labels: `cli`, `docs`, `good first issue`.
   - **Status:** Delivered - `redcon completion <shell>` supports bash, zsh and fish.

5. **Add cache TTL and explicit cache prune command**
   - Support TTL-based cache freshness.
   - Add command to prune expired/unused entries.
   - Labels: `cache`, `cli`, `good first issue`.
   - **Status:** Partial - the Redis backend has a configurable TTL, but there is no TTL freshness for the local cache and no dedicated `cache prune` command yet.

6. **Expose scoring component breakdown in plan output**
   - Show weighted contribution of path/content/import-graph signals.
   - Keep ranking deterministic and explainable.
   - Labels: `scoring`, `reporting`, `good first issue`.
   - **Status:** Delivered - per-file `score_breakdown` in plan output and `run.json`, with a `signals:` line in the human view (1.12.0).

7. **Add HTML renderer for run/diff/benchmark reports**
   - Generate static HTML artifacts for CI and sharing.
   - Keep Markdown/JSON outputs unchanged.
   - Labels: `reporting`, `ci`, `ux`.
   - **Status:** Open - HTML exists only for the import-graph visualizer; run/diff/benchmark reports are still JSON/Markdown.

8. **Policy rule: fail when critical files are skipped**
   - Add configurable threshold for skipped critical files.
   - Integrate with strict mode exit codes.
   - Labels: `policy`, `cli`, `good first issue`.
   - **Status:** Open - critical-path keywords affect scoring, but there is no policy rule that fails on skipped critical files.

9. **Expand examples gallery with one realistic service repo**
   - Add mini repo scenario with reproducible commands and outputs.
   - Keep deterministic results for tests/docs.
   - Labels: `examples`, `docs`, `good first issue`.
   - **Status:** Partial - `examples/` holds several task scenarios and recorded sample outputs; a single dedicated realistic service repo is not yet added.

10. **Add CLI vs Python API parity tests**
    - Verify plan/pack/report parity for equivalent inputs.
    - Protect thin-wrapper contract in CLI.
    - Labels: `tests`, `api`, `good first issue`.
    - **Status:** Delivered - parity tests for plan/pack/report, including matching `prompt_cache_key` across both entry points.

11. **Benchmark mode: add CSV output option**
    - Add optional CSV artifact alongside JSON/Markdown.
    - Preserve current output defaults.
    - Labels: `benchmark`, `reporting`, `good first issue`.
    - **Status:** Delivered - `benchmark --csv` writes a per-strategy CSV; defaults unchanged (1.13.0).

12. **Benchmark mode: compare with previous benchmark artifact**
    - Add baseline input flag and delta summary.
    - Keep deterministic metric definitions.
    - Labels: `benchmark`, `analysis`.
    - **Status:** Delivered - `benchmark --baseline` emits a deterministic per-strategy delta (1.13.0).

13. **Document telemetry event field map and privacy model**
    - Document all event names and payload fields.
    - Clarify explicit opt-in and no-network defaults.
    - Labels: `docs`, `telemetry`, `good first issue`.
    - **Status:** Delivered - `docs/telemetry.md` documents the ten-event field map and the opt-in, no-network, allow-list privacy model.

14. **Add CI recipes for changed-files and strict policy gates**
    - Expand docs with copy-paste workflow examples.
    - Cover pull_request and workflow_dispatch usage.
    - Labels: `docs`, `ci`, `good first issue`.
    - **Status:** Delivered - `docs/ci-recipes.md` has copy-paste workflows for both, on `pull_request` and `workflow_dispatch`.

15. **Improve import-graph test coverage for mixed Python/TS repos**
    - Add realistic fixtures with cross-file relevance propagation checks.
    - Guard against ranking regressions.
    - Labels: `tests`, `scoring`, `good first issue`.
    - **Status:** Delivered - mixed Python/TypeScript fixtures assert within-language propagation and no cross-language edges.

16. **Pluggable token-estimator backend interface** `[Roadmap]`
    - Keep deterministic default estimator.
    - Add clean extension hook for alternate tokenizers.
    - Labels: `core`, `tokens`, `roadmap`.
    - **Status:** Delivered - `TokenEstimatorPlugin` in `redcon/plugins` provides the extension hook; the deterministic heuristic remains the default.

17. **Incremental scan index for repeated runs** `[Roadmap]`
    - Cache scan metadata and skip unchanged files when possible.
    - Maintain output compatibility.
    - Labels: `scanner`, `performance`, `roadmap`.
    - **Status:** Delivered - `.redcon/scan-index` reuses unchanged file metadata (`INDEX_FORMAT_VERSION` 3), output-compatible.

18. **Plugin interface for custom scorers/compressors** `[Roadmap]`
    - Define stable extension points for third-party modules.
    - Avoid breaking CLI and artifact contracts.
    - Labels: `architecture`, `plugins`, `roadmap`.
    - **Status:** Delivered - `ScorerPlugin` and `CompressorPlugin` in `redcon/plugins` with a resolver registry.

19. **Monorepo workspace-root support in config** `[Roadmap]`
    - Support multiple workspace roots and scoped scanning.
    - Keep defaults simple for single-repo usage.
    - Labels: `config`, `scanner`, `roadmap`.
    - **Status:** Delivered - `--workspace` with `load_workspace`/`scan_workspace` scans multiple roots; single-repo defaults unchanged.

20. **Optional LLM-assisted summarization plugin with deterministic fallback** `[Roadmap]`
    - Keep default OSS flow deterministic.
    - Add explicit opt-in plugin path only.
    - Labels: `compressor`, `roadmap`.
    - **Status:** Delivered - opt-in LLMLingua-2 semantic compression via the `redcon[heavy_compression]` extra, with a deterministic passthrough fallback.

## Good First Issues (10)

- #4 Generate shell completions for bash and zsh
- #5 Add cache TTL and explicit cache prune command
- #6 Expose scoring component breakdown in plan output
- #8 Policy rule: fail when critical files are skipped
- #9 Expand examples gallery with one realistic service repo
- #10 Add CLI vs Python API parity tests
- #11 Benchmark mode: add CSV output option
- #13 Document telemetry event field map and privacy model
- #14 Add CI recipes for changed-files and strict policy gates
- #15 Improve import-graph test coverage for mixed Python/TS repos

Across the whole backlog, #5, #7, #8 and #9 remain open or partial (see the
Status lines above); every other issue has shipped.
