# CI Recipes

Copy-paste GitHub Actions workflows for the two most common redcon CI jobs:
targeting a pull request's changed files, and gating context on a strict
policy. Both recipes run on `pull_request` and `workflow_dispatch`, and both
install redcon from PyPI so there is nothing to vendor.

For the fuller pre-built workflow (PR audit, pack, report, artifact upload) see
[github-action.md](github-action.md). For the policy model see
[policy-and-ci.md](policy-and-ci.md).

## Recipe 1: target the pull request's changed files

`redcon pack --changed <paths>` boosts the named files and their one-hop
import-graph neighbours, so a run scoped to a diff surfaces the files the PR
touches even when keyword overlap is weak. On `pull_request` the changed files
come from `git diff`; on `workflow_dispatch` they come from an input.

```yaml
name: redcon-changed-context
on:
  pull_request:
  workflow_dispatch:
    inputs:
      task:
        description: "Task description used for ranking"
        required: true
      changed_files:
        description: "Optional space-separated paths to target"
        required: false

jobs:
  context:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          # Full history so the base..head diff can be computed.
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - run: pip install redcon

      - name: Resolve changed files
        id: changed
        run: |
          if [ "${{ github.event_name }}" = "pull_request" ]; then
            files=$(git diff --name-only --diff-filter=ACMR \
              "${{ github.event.pull_request.base.sha }}" \
              "${{ github.event.pull_request.head.sha }}" | tr '\n' ' ')
          else
            files="${{ github.event.inputs.changed_files }}"
          fi
          echo "files=$files" >> "$GITHUB_OUTPUT"

      - name: Pack context targeting the diff
        env:
          TASK: ${{ github.event.inputs.task || format('Review changes in PR #{0}', github.event.number) }}
        run: |
          redcon pack "$TASK" \
            --repo . \
            --max-tokens 24000 \
            --changed ${{ steps.changed.outputs.files }}
          cat run.md >> "$GITHUB_STEP_SUMMARY"

      - uses: actions/upload-artifact@v4
        with:
          name: redcon-context
          path: |
            run.json
            run.md
```

Notes:

- `--diff-filter=ACMR` drops deleted files from the list; redcon also ignores
  paths that no longer exist, so an unfiltered list is safe too.
- `--changed` is passed unquoted so the space-separated list expands into
  separate arguments. An empty list (no changed files) is valid and simply runs
  a normal ranking.
- Tune the boost with `[score] changed_file_boost` and `changed_neighbor_boost`
  in `redcon.toml`.

## Recipe 2: strict policy gate

`redcon pack --strict --policy <file>` evaluates the packed context against a
policy and exits non-zero when a rule is violated, failing the job. The policy
lives in the repo so the gate is reviewable.

```yaml
name: redcon-policy-gate
on:
  pull_request:
  workflow_dispatch:
    inputs:
      task:
        description: "Task description used for ranking"
        required: true

jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - run: pip install redcon

      - name: Enforce the context budget policy
        env:
          TASK: ${{ github.event.inputs.task || 'Validate the default agent context budget' }}
        run: |
          redcon pack "$TASK" \
            --repo . \
            --max-tokens 24000 \
            --strict \
            --policy .github/redcon-policy.toml
          cat run.md >> "$GITHUB_STEP_SUMMARY"
```

The policy file (`.github/redcon-policy.toml`) uses the standard fields:

```toml
[policy]
max_estimated_input_tokens = 30000
max_files_included = 12
max_quality_risk_level = "medium"
min_estimated_savings_percentage = 0.0
```

On a violation, `pack` prints `Policy check: FAIL` with the offending rules and
exits with code `2`, so the job fails. When every rule passes it prints
`Policy check: PASS` and exits `0`. To gate a previously packed artifact
instead, pass `--policy` to `redcon report <run.json>`: it evaluates the same
policy and exits `2` on a violation (no `--strict` flag needed there).

## Combining the two

The recipes are independent jobs, but they compose: run the changed-files pack
first, then gate the resulting `run.json` with `redcon report run.json --policy
.github/redcon-policy.toml` in a later step. Everything stays deterministic and
local; no network call is made beyond installing redcon.
