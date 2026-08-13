# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.18.0] - 2026-08-14

### Changed

- Adaptive rendering is now **size-aware**: on the largest repositories (the top
  budget band, estimated repository tokens over the last budget step, the
  120k-budget regime), adaptive delivers only the top-ranked files whole and
  compresses the tail, instead of spending the whole budget on a few whole files.
  Smaller and mid-sized repositories are unchanged. Driven by Experiment 4 (see
  `docs/research/exp4-tiered-rendering.md`): on the held-out heavy tasks this
  recovers ground-truth coverage (0.756 vs plain adaptive's 0.363) and lifts the
  parse rate (0.92 vs 0.62), raising heavy one-shot file-overlap above plain
  adaptive - **the trade is a lower heavy line-overlap (fewer whole files) and no
  change on small repositories**. The gate is internal to adaptive with no config
  surface; `--render-mode compressed` still bypasses it. **Packs change on the
  largest repositories, so their `prompt_cache_key` changes once on upgrade;
  smaller repositories are byte-identical. Pin `--render-mode compressed` for the
  pre-1.17.0 pack form.**

### Fixed

- The stdlib gateway now normalizes trailing optional whitespace in bearer tokens
  before comparing them, so both server implementations (FastAPI and the stdlib
  fallback) authenticate the same token identically.

## [1.17.0] - 2026-08-13

### Changed

- Default pack render mode is now **adaptive**: each ranked file is included
  whole when it fits the remaining budget and compressed only on overflow (the
  previous behaviour, always compressing, is still available with
  `--render-mode compressed` or `[render] mode = "compressed"`). This is driven
  by measurement: at equal budget, adaptive-rendered redcon beats both a naive
  whole-file keyword retrieval and the old compressed pack on one-shot edit
  fidelity (file-overlap 0.432 vs 0.319 vs 0.196 pooled; all three pre-registered
  hypotheses hold - see `docs/research/exp3-adaptive-rendering.md`). **Pack
  content changes on upgrade, so packs and their `prompt_cache_key` change once
  and prompt-cache-style caches repopulate; the change is deterministic and one
  time (same class of note as the 1.16 default-budget change). Pin the old
  behaviour with `--render-mode compressed` if you need byte-identical packs.**

## [1.16.0] - 2026-08-09

### Changed

- Scale the default pack budget by repository size. When no budget is set, the
  default grows step-wise with the scanned repository (200k-1M: 45k, 1M-3M: 75k,
  >3M: 120k); small repositories are unchanged. **The default pack budget now
  rises for repositories over ~200k tokens, so packs and their `prompt_cache_key`
  change once after upgrading on medium and large repositories. Users who pin a
  budget with `--max-tokens` or `[budget].max_tokens` are unaffected.** An
  explicit budget that is small for a large repository prints a coverage warning
  to stderr.
- Slim the MCP tool descriptions (about 36% fewer tokens) with a snapshot test
  that caps their size, since they sit in the agent's cached context every
  session.

### Fixed

- Write the redcon instruction block to `CLAUDE.md` when it is missing, not only
  when it already exists. Headless Claude Code reads `CLAUDE.md` but not
  `AGENTS.md`, so the shipped guidance previously never reached it.

### Added

- A pre-registered, two-layer agentic evaluation writeup in
  `docs/research/agentic-eval.md`.

## [1.15.0] - 2026-08-03

### Added

- `redcon doctor` now also reports the license tier and status (never the key or
  its path), the scan-index presence, format version and file count, and the
  cache backend, entry count and TTL with a write-access probe. It additionally
  checks the `pro`, `validate` and `heavy_compression` optional extras.

### Fixed

- `redcon cache prune` no longer drops entries a concurrent process wrote after
  it loaded: the whole read-modify-write runs under the cache file lock and
  re-merges the on-disk state before applying removals.

### Changed

- The launch backlog and roadmap status lines are refreshed to record all 20
  backlog issues as delivered through 1.14.0.

## [1.14.0] - 2026-08-03

### Added

- `redcon cache prune [--repo <path>] [--dry-run] [--json]`: remove expired and
  orphaned entries from the local cache, reporting entries removed and bytes
  freed. Plus `[cache].local_ttl_seconds` (default `0`, disabled) for TTL-based
  freshness of the local cache, mirroring the Redis backend.
- `--html` on `pack`, `diff` and `benchmark`: write a self-contained HTML report
  (inline CSS, no external requests) alongside the JSON and Markdown. The run
  report surfaces per-file `score_breakdown` and `role` and the
  `prompt_cache_key`; the benchmark report includes `baseline_comparison`.
- Policy rule `forbid_skipped_critical_files`: fail when a file matching the
  run's `[score] critical_path_keywords` is scanned but skipped. Disabled unless
  set. The run artifact now carries `critical_path_keywords` so
  `redcon report --policy` can enforce the rule against a recorded run.
- `examples/service-repo`: a small, deterministic orders service with a
  walkthrough of `plan`, `pack` and `validate`, pinned by a test so the docs
  cannot drift.

## [1.13.0] - 2026-08-03

### Added

- Junie CLI as a first-class `redcon mcp install` target: registers the redcon
  MCP server under `mcpServers` in `.junie/mcp/mcp.json` (project) or
  `~/.junie/mcp/mcp.json` (global). Detected when a `.junie` directory exists.
- Cline and Zed as first-class install targets. Cline uses its VS Code
  global-storage `cline_mcp_settings.json` (per-OS path); Zed uses the
  `context_servers` key in `~/.config/zed/settings.json`.
- Versioned JSON Schemas (draft 2020-12) for the `pack` (run), `diff` and
  `benchmark` artifacts under `redcon/schemas/json/v1/`, plus `redcon validate
  <artifact.json>`: picks the schema from the artifact's `command` field, exits
  0 or 1, and can emit machine-readable errors with `--json`. Validation uses a
  built-in checker with no new hard dependency; installing `redcon[validate]`
  swaps in `jsonschema` for full-spec coverage.
- `redcon benchmark --baseline <earlier-benchmark.json>`: a deterministic
  per-strategy delta (input tokens, saved tokens, runtime) against a previous
  benchmark, in the JSON (`baseline_comparison`), Markdown and run summary.
- `redcon benchmark --csv`: an optional per-strategy CSV artifact alongside the
  JSON and Markdown, with baseline and delta columns when `--baseline` is given.
- Each ranked file now carries its `role` (prod/test/docs/example/config/
  generated) in `run.json` and plan output, shown as a `[role]` tag in the
  human plan view.

### Changed

- The file role is classified once at scan time and cached in the scan index
  (`INDEX_FORMAT_VERSION` bumped to 3) instead of being recomputed per run.
- `redcon mcp install` refuses to overwrite a config file that exists but does
  not parse as JSON (for example a Zed `settings.json` with comments), reporting
  a failed status with manual-add instructions instead of replacing the user's
  configuration. Missing or empty files are still created or filled.

## [1.12.0] - 2026-08-03

### Added

- `--changed PATH ...` on `plan` and `pack`: boost the named files and their
  import-graph neighbours in ranking, so a task scoped to a diff surfaces the
  files it touches. Deterministic.
- Per-file `score_breakdown` in `plan` output, `run.json`, and the human plan
  view: the weighted contribution of each ranking signal (path/content
  keywords, symbols, import-graph, role and changed-file boosts). Deterministic.

### Changed

- Max compression profile is now free for everyone.

## [1.11.4] - 2026-07-30

### Fixed

- Pin the `mcp` extra to `mcp>=1.0,<2.0`. The MCP server uses the mcp 1.x
  `Server` API (`@server.list_tools()`), which mcp 2.0.0 removed, so
  `redcon[mcp]` crashed on start with fresh installs. Pinned to 1.x.


## [1.11.3] - 2026-07-30

### Added

- MCP Registry ownership marker (`mcp-name`) in the README, and a root
  `server.json`, so redcon can be published to the official MCP Registry.


## [1.11.2] - 2026-07-28

### Changed

- Rotated the embedded Ed25519 license verification key. Pro licenses are
  issued under the new key; licenses signed against the previous key no longer
  verify and must be re-issued.

## [1.11.1] - 2026-07-27

### Added

- `prompt_cache_key` in run reports and pack output: a stable 16-hex
  fingerprint of the packed (path, text) sequence. An unchanged tree and task
  reproduce the same key and edits outside the pack keep it warm, so callers
  can key provider prompt caches on it and detect real prefix changes.
- Production license verification key embedded; Pro licenses purchased
  for 1.11.1 and later activate offline with `redcon license --activate`.

### Fixed

- `redcon --version` (and `redcon.__version__`) now reads the installed
  package metadata instead of a hardcoded string, which had lagged behind
  the released version.

## [1.11.0] - 2026-07-23

### Added

- Compression profiles: `redcon pack --compression-profile max` (Pro) applies
  tighter tier thresholds end to end and reports `Profile: max compression
  (Pro)` in the output; without a license the run falls back to the default
  profile with a warning. Configurable via `profile` in `redcon.toml`.
- `redcon license` command: `--activate KEY` stores the license, plain
  invocation shows plan, status and expiry, `--deactivate` removes it.
- `docs/methodology.md`: reproducible measurement procedure behind the
  published savings numbers.

- Five new cmd-side compressors: `kubectl_events` (specialised inside
  KubectlGetCompressor for event-shape headers, 91.5% reduction),
  `profiler` (py-spy / perf collapsed-stack, 90%), `json_log` (NDJSON
  with schema-mining, 91%), `coverage` (lowest-coverage top-K, 73%),
  `sql_explain` (Postgres + MySQL TREE, 71%), `bundle_stats` (webpack
  + esbuild metafiles, 84%). Total now 16 cmd compressors.
- V47 schema-aware delta dispatcher with structured renderers for
  pytest (set-diff over failure names + count delta), git_diff
  (file-set + per-file +/- counts), coverage (per-file pp moves above
  0.5pp threshold). Generic line-delta is the fallback.
- V41 session-scoped path aliasing layer (`PathAliaser`); first-use
  binding `f001=path` then bare alias on later mentions, scoped to
  callers passing a session aliaser into `compress_command`.
- V93 invariant-cert sha prefix `mp_sha=<16hex>` stamped on
  COMPACT/VERBOSE outputs; upgrades must-preserve from existence to
  set-equality so auditors can detect spurious additions.
- V62 lint rule-pivot COMPACT layout chosen by min-gate vs the existing
  per-file layout. Wins on Zipfian distributions with >=3 codes.
- V51 stratified file-balanced sampling for >30 test failures (still
  preserves every failing name in a tail summary).
- V64 generic skeleton-clustering helper (`_skeletons.py`) reused by
  pytest cluster path and exposed for future trace compressors.
- V31 24-entry tokenizer-aware substitution table applied at
  compact/ultra tier with re-tokenisation gate.
- V32 whitespace tightening (`,` and `:` gap collapse) post
  `_normalise_whitespace`.
- V38 NO_COLOR / TERM=dumb env injection in runner plus ANSI / OSC /
  CR-overwrite stripper pre-compress.
- 100-vector research corpus under `research/` (BASELINE.md, INDEX.md,
  SYNTHESIS.md, plus one note per V01..V100).

### Changed

- README compressor table extended to 15 schemas (was 11) and includes
  a new "Cross-call dimension" subsection covering V41/V47/V93.
- `redcon cmd-bench` baseline (`benchmarks/cmd_baseline.json`) now
  covers all 16 schemas / 75+ axes; per-schema markdown reports under
  `docs/benchmarks/cmd/` regenerated.
- `verify_must_preserve` now memoises compiled patterns (V78), so
  per-call dynamic must-preserve sets stop thrashing `re._cache`.
- `git_diff`, `git_log`, `git_status` and `coverage` build their
  must-preserve patterns from parsed entries rather than static regex,
  so adversarial mutation no longer trips the contract.
- V85 adversarial GA fuzzer expanded to all 16 compressors with a
  deterministic per-test seed (sha1, not built-in hash); `_NOT_YET_
  ENFORCED` set is empty so `REDCON_V85_ENFORCE=1` is a hard CI gate
  for every shipped compressor.

### Fixed

- FastAPI gateway resolves the Authorization header reliably under
  `from __future__ import annotations` and returns a consistent JSON error
  contract (400 with `{"error": ...}` for malformed bodies).
- Concurrent summary-cache writers merge per key under a file lock instead of
  last-writer-wins.
- `last_run_artifact` survives session serialization in the gateway store.
- ANSI sequences and CR-overwrite progress bars no longer bleed into
  compressed output (V38).
- `git_status`, `json_log`, `bundle_stats` fall through to raw
  passthrough when the structured form would inflate (non-regressive
  guard for adversarial noise).
- Empty-subject `git log` rows now emit `commit <short_sha>` instead
  of collapsing to a bare `<short_sha>` line.
- ls/tree/find must-preserve patterns aligned with the formatter's
  per-directory slicing - basenames the formatter actually emits, not
  full nested paths.
- Removed inline `re.match` / `re.search` calls in `symbols.py`,
  `tree_sitter.py`, and `sql_explain_compressor.py` per the V78 audit.

## [1.1.0] - 2026-03-18

### Added

- Per-signal score breakdown in RankedFile
- Go import graph support
- License header and docstring skipping in deterministic summarizer

### Changed

- Extracted shared file patterns, fixed types, updated SDK

### Fixed

- TOML config loading, file-role substring matching, and degradation test

## [1.0.0] - 2026-03-01

### Added

- Initial public release
- Deterministic context budgeting engine
- CLI with plan, pack, report, diff, benchmark, heatmap, and watch commands
- Workspace support for multi-repo and monorepo-package workflows
- Agent middleware layer
- Plugin system for scorers, compressors, token estimators, and summarizers
- GitHub Action for CI integration
- Docker image
- Redcon Cloud gateway (commercial)
