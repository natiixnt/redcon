# Telemetry Architecture

## Purpose

Redcon includes a telemetry abstraction so future integrations can route run metrics
to different sinks without changing pipeline logic.

Current behavior remains local-first:
- telemetry is disabled by default (`enabled = false`, sink `noop`)
- nothing is written or sent unless you explicitly enable it
- no hidden data collection exists

## Components

- `TelemetrySink` interface (`redcon.telemetry`)
- `NoOpTelemetrySink` default implementation
- `JsonlFileTelemetrySink` local development sink
- `HttpTelemetrySink` opt-in network sink: POSTs events to a Redcon Cloud
  ingestion endpoint. Only active when you explicitly set `sink = "cloud"`
  (or `"http"`); the endpoint comes from `redcon.toml` or `REDCON_CLOUD_URL`.
  Delivery is best-effort and never interrupts the pipeline.
- `TelemetrySession` run-scoped emitter with shared context fields

## Event Model

Events are structured JSON objects:

```json
{
  "name": "pack_completed",
  "schema_version": "v1",
  "timestamp": "2026-03-12T20:00:00+00:00",
  "run_id": "f6b1...",
  "payload": {
    "command": "pack",
    "repository": {
      "repository_id": "sha256:...",
      "workspace_id": "sha256:..."
    },
    "tokens": {
      "estimated_input_tokens": 1240
    }
  }
}
```

## Event envelope

Every event is one JSON object with a fixed envelope and a `payload`:

| Field | Meaning |
| --- | --- |
| `name` | the event name (see the field map below) |
| `schema_version` | analytics schema version, currently `v1` for all events |
| `timestamp` | ISO-8601 UTC time the event was recorded |
| `run_id` | random per-run identifier tying a run's events together |
| `payload` | the per-event fields, described below |

Two payload fields are shared by the run/scan/pack/plan events:

- `command` - the command that produced the event, for example `"pack"`,
  `"plan"`, `"benchmark"`. An enum-like string, not free text.
- `repository` - `{ "repository_id": "sha256:...", "workspace_id": "sha256:..." }`.
  These are SHA-256 digests of the resolved repo/workspace path, never the raw
  path (see [Trust and Privacy](#trust-and-privacy)).

## Event field map

The pipeline emits ten event types. Payloads are rebuilt from a fixed
allow-list before recording, so only the fields below are ever written - counts,
token estimates, and enum-like status strings. The values a call site passes
that are not listed here (task text, raw paths) are dropped.

| Event | Emitted when | Recorded `payload` fields (beyond `command` + `repository`) |
| --- | --- | --- |
| `run_started` | a run begins | `tokens.max_tokens`, `files.top_files` |
| `scan_completed` | repository scan finishes | `files.scanned_files` |
| `scoring_completed` | relevance scoring finishes | `files.scanned_files`, `files.ranked_files`, `files.top_files` |
| `plan_completed` | a `plan` run finishes | `files.scanned_files`, `files.ranked_files`, `files.top_files`, `tokens.estimated_input_tokens` |
| `pack_completed` | a `pack` run finishes | `tokens.{max_tokens, estimated_input_tokens, estimated_saved_tokens}`, `files.{scanned_files, ranked_files, included_files, skipped_files, top_files}`, `cache.{cache_hits, duplicate_reads_prevented}`, `quality_risk_estimate` |
| `cache_hit` | cached content is reused | `cache.{cache_hits, tokens_saved, backend, fragment_hits, fragment_misses}` |
| `delta_applied` | a delta pack is emitted | `delta.{files_added, files_removed, files_changed, delta_tokens, tokens_saved, has_previous_run, slices_changed, symbols_changed}` |
| `benchmark_completed` | a `benchmark` run finishes | token estimates, file counts, `benchmark.scan_runtime_ms`, and per-strategy summaries (strategy name plus numeric metrics; strategy file lists are reduced to counts) |
| `policy_failed` | a strict policy evaluation fails | `tokens`, file counts, `cache`, `quality_risk_estimate`, `policy.{evaluated, passed, violation_count, violations, checks, failing_checks}` |
| `policy_violation` | fires together with `policy_failed` | same fields as `policy_failed` |

`policy.violations` and `policy.checks` carry policy-rule names and messages you
authored in the policy file; they contain no repository content.

## Configuration

Telemetry is configured via `redcon.toml`:

```toml
[telemetry]
enabled = true
sink = "file"
file_path = ".redcon/telemetry.jsonl"
```

Defaults:
- `enabled = false`
- `sink = "noop"`
- `file_path = ".redcon/telemetry.jsonl"`

Accepted sink values: `noop` (or `none`), `file` (aliases `jsonl`,
`jsonl_file`) for the local JSONL file, and `cloud` (alias `http`) for the
opt-in network sink described above.

## Trust and Privacy

Explicit opt-in, no network by default:

- Telemetry is off by default (`enabled = false`, `sink = "noop"`). With the
  default, no event is written or sent anywhere.
- The only sink that makes a network call is `cloud`/`http`, and it is used
  only when you set it explicitly. `REDCON_CLOUD_URL` merely chooses the URL for
  that sink; it does not enable telemetry on its own.
- The `file` sink writes only to a local path you control (default
  `.redcon/telemetry.jsonl`).

Two mechanisms keep payloads free of sensitive data, by construction:

- **Path hashing.** Repository and workspace paths are recorded only as
  `sha256:<digest>` identifiers, never as raw paths.
- **Allow-list rebuild.** Before an event is recorded, its payload is rebuilt
  from a fixed allow-list of numeric and enum-like fields (see the field map).
  Anything a call site passes that is not on the list - task text, raw file or
  workspace paths, file contents - is dropped and never written.

As a result, recorded payloads contain counts, token estimates, cache
statistics, and status strings only. The only longer strings that can appear
are policy-rule names and messages from your own policy file.

## Not part of this event stream

- `redcon observe` keeps a separate local run-history file
  (`.redcon/observe-history.json`); it is not routed through the telemetry
  sink and never leaves the machine.
- The optional gateway has its own event hooks, but no emitting sink is wired
  to them by default, so gateway events are dropped unless a sink is injected
  programmatically. They do not apply the allow-list rebuild above, so a custom
  gateway sink would be responsible for its own redaction.
