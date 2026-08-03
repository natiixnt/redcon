# Cache

Redcon is local-first by default. The source-available build ships cache backend abstractions so the pack pipeline can stay stable as teams add stricter trust boundaries or future shared cache integrations.

## Built-in Backends

- `local_file`: default backend. Persists summary previews to `.redcon_cache.json` inside the repo.
- `redis`: production-ready shared cache cluster backend. Stores compressed context entries in Redis with configurable TTL and namespace isolation.
- `shared_stub`: no-op shared/remote backend stub. It exercises the shared-cache interface without making network calls or persisting hosted state.
- `memory`: process-local backend intended for tests and advanced embedders.

## Local Cache

The default backend stores summary previews on disk and reuses them on later runs. This keeps OSS behavior local, deterministic, and inspectable.

```toml
[cache]
backend = "local_file"
summary_cache_enabled = true
cache_file = ".redcon_cache.json"
duplicate_hash_cache_enabled = true
```

`run.json` records cache details in a top-level `cache` block:

```json
{
  "cache": {
    "backend": "local_file",
    "enabled": true,
    "hits": 3,
    "misses": 1,
    "writes": 1
  },
  "cache_hits": 3
}
```

`cache_hits` remains as a compatibility field for existing consumers.

### TTL freshness

The local cache does not expire entries by default, so behavior is unchanged
unless you opt in. Set a positive `local_ttl_seconds` under `[cache]` to treat
entries older than that many seconds as stale (a cache miss), mirroring the
Redis backend's `redis_ttl_seconds`. `0` disables expiry.

```toml
[cache]
backend = "local_file"
local_ttl_seconds = 86400   # expire local cache entries after 24 hours; 0 = never
```

Entries written before TTL was enabled have no recorded timestamp and are
treated as fresh, so turning TTL on never retroactively drops existing entries.

### Pruning

`redcon cache prune` removes stale entries from the local cache:

```bash
redcon cache prune --repo .            # remove expired and orphaned entries
redcon cache prune --repo . --dry-run  # report what would be removed, change nothing
redcon cache prune --repo . --json     # machine-readable summary
```

It removes two kinds of entries:

- **Expired** - older than `local_ttl_seconds` (only when TTL is enabled).
- **Orphaned** - the file the entry was cached for no longer exists in the repo.
  A wrong or empty repository path never removes orphaned entries, so prune
  cannot wipe the whole cache by mistake.

The command prints how many entries were removed and how many bytes were freed
(`entries_removed`, `bytes_freed`, `expired`, `orphaned`). Running it on a cache
with nothing expired or orphaned is a no-op and leaves the file untouched.

## Redis Shared Cache Cluster

The `redis` backend enables multiple agents or CI runs to share cached summaries, context slices, and compressed fragments across machines.

```toml
[cache]
backend = "redis"
redis_url = "redis://your-redis-host:6379/0"
redis_namespace = "myorg:myrepo"
redis_ttl_seconds = 86400
```

Install the extra dependency:

```
pip install "redcon[redis]"
```

### Cache key structure

Keys embed repository, file path, symbol, and content hash so that multiple agents working on the same codebase share entries without collisions:

```python
from redcon.cache import build_redis_cache_key

key = build_redis_cache_key(
    org="myorg",
    repo="backend",
    file_path="src/auth.py",
    symbol_or_slice="def login",
    content_hash=sha256(content.encode()).hexdigest(),
)
cache.get_fragment(key)
```

### Stored entry types

| Type | Store prefix | Description |
|------|-------------|-------------|
| Symbol summaries | `s:` | Compressed prose summaries of individual symbols |
| Context slices | `c:` | Verbatim or summarized slices of file regions |
| Compressed fragments | `f:` | Reusable compressed context fragments |

All values are zlib-compressed before storage.

### TTL and invalidation

TTL is set per entry via `redis_ttl_seconds` (default 86400 s / 24 h). Set to `0` to store without expiry.

Explicit invalidation:

```python
# Remove one logical key across all stores
backend.invalidate("fragment:src/auth.py:10-30:abc123")

# Remove every entry in this backend's namespace (e.g. after a force-push)
backend.invalidate_namespace()
```

### Metrics

The `cache` block in `run.json` includes per-store counters:

```json
{
  "cache": {
    "backend": "redis",
    "enabled": true,
    "hits": 5,
    "misses": 2,
    "writes": 2,
    "tokens_saved": 840,
    "fragment_hits": 3,
    "fragment_misses": 1,
    "fragment_writes": 1,
    "slice_hits": 2,
    "slice_misses": 1,
    "slice_writes": 1
  }
}
```

## Future Shared Cache Direction

`shared_stub` exists to make the cache boundary explicit today without shipping hosted infrastructure. It deliberately behaves as a deterministic miss-only backend:

- no network calls
- no hidden background sync
- no hosted service dependency
- no implicit trust expansion

Future team-level reuse can plug into the same backend interface under `redcon/cache/` without changing CLI contracts or the `run.json` artifact shape.

## Trust And Privacy

Cache entries are derived from repository contents. Treat them as sensitive code-adjacent data.

- Keep `local_file` when repository data must remain on the current machine.
- Only adopt a future shared backend if the cache operator is allowed to see the same repository content as the developers using it.
- Telemetry and cache are separate systems. Telemetry stays opt-in, disabled by default, and has no network sink in OSS.
- The shared-cache stub in OSS sends nothing anywhere.
