# Contributing

## Setup

```bash
python -m pip install -e .[dev]
pytest
```

## Guidelines

- Keep runtime dependencies minimal.
- Preserve deterministic behavior in core scoring/compression.
- Add tests for every behavior change.
- Avoid introducing model-provider coupling in core modules.

## Pull Requests

Include:
- problem statement
- approach and tradeoffs
- test coverage updates
- before/after sample report if behavior changes

## Releasing

Per version (from 1.11.1 on):

1. Bump `version` in `pyproject.toml` (single source; `redcon/__init__.py`
   reads it from installed metadata).
2. Move `CHANGELOG.md` `[Unreleased]` into a dated `[X.Y.Z]` section.
3. Open a PR to `main`, wait for green CI, rebase-merge.
4. Tag `vX.Y.Z` and push it. The `release.yml` workflow builds and publishes
   the wheel to PyPI and creates the GitHub Release; the tag must match the
   `pyproject.toml` version (the workflow enforces this on manual runs).
5. Verify the published wheel from a clean venv:
   - `pip install redcon==X.Y.Z`, then `redcon --version` matches.
   - `python -c "import redcon; print(redcon.__version__)"` matches too (the
     path that regressed in 1.11.0).
6. Bump `version` in `server.json` (root) and run `mcp-publisher publish` to
   update the MCP Registry entry.
7. Only when the VS Code extension changed: `vsce publish` for `vscode-redcon`.
