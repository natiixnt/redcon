# Example service repo

A small, deterministic orders service used to show redcon on a realistic
codebase: a layered Python service (API, business logic, persistence, auth,
events) with tests and config. Everything here is fixed, so the commands below
reproduce the same output every time.

## Layout

```
service-repo/
  redcon.toml            # critical_path_keywords = ["auth"], local cache TTL
  pyproject.toml
  src/orders/
    api.py               # request handlers        -> service, auth
    service.py           # create / pay / cancel    -> repository, events, models
    repository.py        # persistence              -> db, models
    auth.py              # bearer-token auth (critical path)
    models.py  db.py  events.py  config.py  errors.py
    main.py              # entrypoint wiring it together
  tests/                 # test_api / service / repository / auth / models
```

The modules import each other (api -> service -> repository -> db), so redcon's
import graph propagates relevance across the layers.

## Reproduce

Run these from the repository root. All outputs are deterministic.

### 1. Rank the files a task touches

```bash
redcon plan "add an order cancellation endpoint" --repo examples/service-repo
```

The top-ranked files, in order, are:

```
1. src/orders/api.py
2. src/orders/repository.py
3. src/orders/service.py
4. src/orders/main.py
5. src/orders/models.py
```

`api.py` (the handler layer), `service.py` (which owns `cancel_order`) and
their import neighbours rise to the top; the leaf `models.py` follows.

### 2. Pack context under a budget

```bash
redcon pack "add an order cancellation endpoint" --repo examples/service-repo --max-tokens 8000
```

Writes `run.json` and `run.md`. The pack fits the whole service (18 files) well
under the 8000-token budget and reports a `low` quality risk. Add `--html` for a
self-contained `run.html` report.

### 3. Validate the artifact

```bash
redcon validate run.json
```

Prints `valid run artifact` and exits `0`, so the pack output can be gated in CI.

## What the config demonstrates

`redcon.toml` sets `critical_path_keywords = ["auth"]`, so `auth.py` is treated
as a critical path. Combined with a policy that sets
`forbid_skipped_critical_files = true`, a pack that ranked `auth.py` out of the
budget would fail the check. It also sets `local_ttl_seconds`, so
`redcon cache prune --repo examples/service-repo` reports and removes stale
cache entries.

## Determinism

redcon is deterministic: the same tree and task always produce the same ranking
and the same `prompt_cache_key`, so this example's output does not drift. The
project test suite pins the ranking above.
