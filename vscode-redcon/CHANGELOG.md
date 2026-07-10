# Changelog

## 0.9.0 - 2026-07-10

### Added

- Savings section at the top of the dashboard: cumulative tokens saved
  across recent runs with an estimated dollar amount, plus a per-run
  savings trend chart with hover details. The dollar conversion uses
  the new `redcon.costPerMillionTokens` setting (default 3.0 USD).
- Status bar now shows tokens saved next to budget usage after a run.

### Changed

- Dashboard redesign: data colors moved to a validated palette with
  separate light and dark steps (the old hardcoded dark-theme colors
  were washed out or invisible in light themes, and the navy
  symbol-extraction slice was invisible in dark ones). Buttons, links
  and hover tooltips now use native VS Code theme tokens.
- Fixed the budget donut center label rendering rotated 90 degrees.
- Strategy colors are assigned per strategy name and stay stable
  across runs instead of depending on which strategies appear.
- File ranking score bars use a single hue instead of traffic-light
  coloring by rank.

### Internal

- Dashboard HTML rendering extracted to a pure module
  (`webview/dashboardHtml.ts`) with no dependency on the vscode API,
  so it can be rendered and tested standalone.

## 0.8.0 - 2026-04-27

### Added (delivered by the underlying Redcon CLI)

- Five new cmd-side compressors the extension's `Redcon: Run Command`
  workflow now picks up automatically: `kubectl_events`, `profiler`
  (py-spy + perf collapsed-stack), `json_log` (NDJSON schema-mining),
  `coverage` (coverage report), `sql_explain` (Postgres + MySQL TREE),
  and `bundle_stats` (webpack + esbuild metafiles). Total now 16
  compressors visible to the dashboard's per-schema reduction view.
- Cross-call session dimension:
  - V41 path aliases collapse repeated paths to short `f001` form
  - V43 reference ledger replaces repeated paragraph blocks with
    session-stable `{ref:001}` markers
  - V47 snapshot-delta dispatcher with schema-aware renderers for
    pytest (set-diff over failure names), git_diff (file-set diff),
    and coverage (per-file pp moves)
  - V49 symbol aliases collapse repeated CamelCase / snake_case
    identifiers to `c001`
  - V93 invariant-cert sha-prefix stamped on COMPACT/VERBOSE outputs
- V85 adversarial GA fuzzer covers all 16 compressor schemas as a
  hard CI gate when `REDCON_V85_ENFORCE=1`.

### Changed

- VS Code marketplace metadata bumped to reflect the broader compressor
  ecosystem; no breaking surface changes in the extension itself.

## 0.7.5 - 2026-03-30

- Glass-style setup UI, centered logo.

## 0.7.0 - 2026-03-29

- One-click setup for Redcon CLI and MCP server.
- Auto-install MCP config for Claude Code, Cursor, Windsurf.

## 0.1.0 - 2026-03-18

### Added

- Activity bar with 4 panels: Budget, File Ranking, Packed Context, Run History
- Status bar with live token budget gauge and quality risk indicator
- File decorations showing relevance scores in the Explorer
- CodeLens showing compression strategy and token savings above files
- Dashboard webview with KPI cards, budget gauge, bar charts, and tables
- 14 commands: Pack, Plan, Plan Agent, Doctor, Init, Export, Benchmark, Simulate, Drift, Dashboard, Config, Copy Context, Refresh, Reveal File
- 9 configurable settings for CLI path, budget, display options
- 6 custom theme colors for score tiers and budget indicators
- Welcome views with quick-start links
- Auto-detection of Redcon CLI installation
- Run history loading from workspace artifacts
