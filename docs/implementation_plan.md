# Cache Completion Plan — Tomorrow's Work Order

## Current State (What Exists Today)

| File | Status | Notes |
|---|---|---|
| `serpapi_cache/cache.py` | ✅ Logic correct | Dosage guard added, query_text passed |
| `serpapi_cache/backends.py` | ✅ Complete | InMemory + Redis both store query_text |
| `scripts/verify_cache.py` | ⚠️ Needs update | Tests use laptop/GDP queries, no dosage tests |
| `scripts/tune_threshold.py` | ❌ Wrong domain | Laptop/GDP pairs — not pharma |
| `docker-compose.yml` | ❌ Missing | Not created yet |
| `tests/` directory | ❌ Missing | All tests currently inline in verify_cache.py |

---

## Bugs Found During Code Review

> [!CAUTION]
> These must be fixed before any test is run — they will cause failures.

**B1 — `cache.py` line 82: Default backend is still `InMemoryBackend()`**
The constructor does `backend or InMemoryBackend()`. There is no auto-detect logic.
If no backend is passed, it silently uses in-memory (no warning, no Redis attempt).
This must be updated to: try Redis → if connection fails → warn + fallback to InMemory.

**B2 — `verify_cache.py` Stage 2: Persistence test is incomplete**
Test 3 in Stage 2 creates a new `SerpApiCache` instance pointing at the same Redis,
but `call_count` is shared from the same process. This does not prove cross-process
persistence. The real persistence test requires: write → kill Python → restart Python
→ read. The test as written is a weak proxy.

**B3 — `verify_cache.py` Stage 1: No dosage guard tests**
The dosage guard was added to `cache.py` today. There are zero tests for it.
A query like "Metformin 20mg" vs "Metformin 200mg" must be explicitly verified.

**B4 — `verify_cache.py` Stage 3: Uses in-memory backend, not Redis**
Stage 3 (real API test) creates `InMemoryBackend()`. This means real API results are
never persisted to Redis. The judge demo needs to show that real pharma searches
persist in Redis after the session ends.

**B5 — `tune_threshold.py`: No dosage-confusion pairs**
The threshold tuner does not test the critical case: same drug, different dosage.
"Metformin 500mg" vs "Metformin 500 mg" should HIT. "Metformin 20mg" vs
"Metformin 200mg" must be handled by the dosage guard, not the threshold.
Both cases need to be present in the tuner output.

---

## What to Build Tomorrow

### Step 1 — `docker-compose.yml` (5 min)

Create at repo root. Single Redis container with AOF persistence so data
survives `docker compose down && docker compose up -d`.

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
volumes:
  redis_data:
```

Run command: `docker compose up -d`

---

### Step 2 — Fix B1: Auto-detect Redis in `cache.py` (10 min)

Replace line 82 in `cache.py`:

```python
# BEFORE (silent, no warning)
self.backend: BaseBackend = backend or InMemoryBackend()

# AFTER (auto-detect with clear log)
if backend is not None:
    self.backend = backend
else:
    self.backend = self._auto_detect_backend()
```

Add private method `_auto_detect_backend()`:

```python
@staticmethod
def _auto_detect_backend() -> BaseBackend:
    try:
        from .backends import RedisBackend
        b = RedisBackend(host="localhost", port=6379)
        return b  # prints "✅ Redis connected at localhost:6379"
    except Exception:
        import warnings
        warnings.warn(
            "\n⚠️  Redis not reachable at localhost:6379. "
            "Falling back to InMemoryBackend — data will NOT persist across restarts.\n"
            "   Start Redis: docker compose up -d",
            stacklevel=3,
        )
        return InMemoryBackend()
```

This makes the backend choice **visible** — judge / you always knows which one is active.

---

### Step 3 — Create `tests/` directory (30 min)

Move all test logic out of `verify_cache.py` into a clean `tests/` structure.
`verify_cache.py` becomes a thin runner.

```
tests/
├── __init__.py              ← empty
├── test_in_memory.py        ← Stage 1 logic (no Redis, no API key needed)
├── test_redis.py            ← Stage 2 logic (Redis required)
├── test_dosage_guard.py     ← NEW: dosage guard unit tests
└── test_persistence.py      ← NEW: true cross-instance persistence test
```

#### `tests/test_dosage_guard.py` — Exact tests needed

```python
# T1: Same drug, same dosage, different phrasing → MUST HIT
cache.search(q="Metformin 500mg price India")
cache.search(q="Metformin 500 mg cost India")
# assert: call_count == 1 (HIT, dosage numbers match: both have {500})

# T2: Same drug, DIFFERENT dosage → MUST MISS (dosage guard fires)
cache.search(q="Metformin 20mg price India")
cache.search(q="Metformin 200mg price India")
# assert: call_count == 2 (MISS, {20} != {200})

# T3: Different drug, similar name → MUST MISS (different numbers + low cosine)
cache.search(q="Atorvastatin 10mg price India")
cache.search(q="Atorvastatin 20mg price India")
# assert: call_count == 2 (MISS, {10} != {20})

# T4: No number in query → dosage guard skipped, pure cosine decides
cache.search(q="cheap diabetes medicine India")
cache.search(q="affordable diabetes drugs India")
# assert: call_count == 1 (HIT via cosine, no numbers to guard)

# T5: Edge case — decimal dosage (2.5mg vs 5mg)
cache.search(q="Amlodipine 2.5mg tablet price")
cache.search(q="Amlodipine 5mg tablet price")
# assert: call_count == 2 (MISS, {2.5} != {5})
```

#### `tests/test_persistence.py` — True cross-instance test

```python
# Instance A writes to Redis
cache_a = SerpApiCache(api_key="test", backend=RedisBackend())
cache_a._call_serpapi = fake_serpapi
cache_a.search({"q": "Metformin 500mg price India", "engine": "google"})
# assert: cache_a.size() == 1

# Instance B — new Python object, same Redis process
cache_b = SerpApiCache(api_key="test", backend=RedisBackend())
cache_b._call_serpapi = fake_serpapi_b  # fresh call counter
cache_b.search({"q": "Metformin 500mg price India", "engine": "google"})
# assert: call_count_b == 0 (HIT from Redis, not re-fetched)
# assert: cache_b.size() == 1

# Cleanup
cache_a.flush()
```

---

### Step 4 — Update `verify_cache.py` (15 min)

- Stage 1 imports and calls `tests/test_in_memory.py`
- Stage 2 imports and calls `tests/test_redis.py` + `tests/test_persistence.py`
- **Fix B4**: Stage 3 (real API) uses `RedisBackend` not `InMemoryBackend`
- Stage 3 adds a new sub-test: after real API call, kill cache object, create new one,
  prove the result is still in Redis without another API call

---

### Step 5 — Update `scripts/tune_threshold.py` (10 min)

Replace all query pairs with pharma-specific ones. Add a dosage guard column
to the output so it's visible which pairs are blocked by guard vs threshold.

**Pairs to include:**

| Pair | Expected | Why |
|---|---|---|
| `Metformin 500mg price India` ↔ `Metformin 500 mg cost India` | HIT | Same dosage, same drug |
| `Atorvastatin 10mg tablet price` ↔ `Atorvastatin 10 mg cost India` | HIT | Same dosage phrasing |
| `cheap Paracetamol 500mg India` ↔ `affordable Paracetamol tablet India` | HIT | No numbers in second, cosine decides |
| `generic substitute for Januvia India` ↔ `Januvia generic alternative India` | HIT | Semantic match |
| `Metformin 20mg price India` ↔ `Metformin 200mg price India` | MISS | Dosage guard: {20} ≠ {200} |
| `Atorvastatin 10mg` ↔ `Atorvastatin 20mg` | MISS | Dosage guard: {10} ≠ {20} |
| `Metformin 500mg price India` ↔ `Amlodipine 5mg price India` | MISS | Different drug |
| `Levothyroxine 50mcg price` ↔ `Atorvastatin 10mg tablet price` | MISS | Completely different |

Output should show: Score | Dosage-Guard-Fired? | Verdict | Expected | Pass/Fail

---

## Execution Order Tomorrow

```
1. Launch Docker Desktop
2. docker compose up -d          ← starts Redis on :6379
3. Fix B1 in cache.py            ← auto-detect backend
4. Create docker-compose.yml
5. Create tests/__init__.py
6. Create tests/test_in_memory.py
7. Create tests/test_dosage_guard.py
8. Create tests/test_redis.py
9. Create tests/test_persistence.py
10. Update verify_cache.py       ← thin runner, fix B4
11. Update tune_threshold.py     ← pharma pairs
12. python scripts/verify_cache.py --offline   ← Stage 1 + dosage tests
13. python scripts/verify_cache.py             ← Stage 1 + 2 + persistence
14. python scripts/tune_threshold.py           ← threshold analysis output
```

---

## Open Questions for Tomorrow

**OQ1 — Threshold decision**: After running `tune_threshold.py` with pharma pairs,
decide whether to use 0.80 (current) or 0.82 (proposed). The output table will
make this obvious.

**OQ2 — TTL for pharma**: Medicine prices change daily on 1mg/PharmEasy.
1 hour TTL may be too long for production. Consider 30 min for price queries,
24 hours for generic substitute queries (which change rarely).
This does not block cache completion — set as a configurable parameter.

**OQ3 — Redis password**: For the hackathon demo, no password is fine.
For the `docker-compose.yml`, note that no auth is set. Don't add it now.

---

## Definition of Done for Cache Phase

- [ ] `docker compose up -d` starts Redis
- [ ] `SerpApiCache()` with no args prints which backend is active
- [ ] `python scripts/verify_cache.py --offline` — all Stage 1 + dosage tests pass
- [ ] `python scripts/verify_cache.py` — Stage 2 persistence test passes
- [ ] `python scripts/tune_threshold.py` — all pharma pairs show correct verdict
- [ ] Dosage guard: "Metformin 20mg" vs "Metformin 200mg" always shows MISS
- [ ] Threshold pairs: "Metformin 500mg" vs "Metformin 500 mg" always shows HIT
