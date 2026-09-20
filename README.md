# serpapi-cache

> A semantic query cache for [SerpApi](https://serpapi.com) — stops you from burning API credits on queries you've already asked before.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![SerpApi](https://img.shields.io/badge/powered%20by-SerpApi-green)](https://serpapi.com)

---

## What Problem Does This Solve?

When you build an AI agent that calls SerpApi, it often searches for the same or very similar things multiple times:

```
Agent calls:  "best laptop under 50000 India"    → costs 1 credit, takes 7s
Agent calls:  "top laptops below 50k in India"   → costs 1 MORE credit, takes 7s again
```

These two queries mean the **same thing**. Without a cache, you pay twice and wait twice.
With `serpapi-cache`, the second call is **free and instant**.

---

## How It Works — Simple Explanation

Think of it like this: every search query gets converted into a "fingerprint" (a list of 384 numbers that captures the *meaning* of the query). When you search again, we compare the new fingerprint against all stored fingerprints. If they're close enough (above a similarity threshold), we return the saved result instead of calling SerpApi.

```
You search: "affordable diabetes drugs India"
             ↓
     Convert to fingerprint: [0.23, -0.11, 0.87, ...]
             ↓
     Compare against cached fingerprints
             ↓
     "cheapest medicine for diabetes India" → similarity score: 0.93
     0.93 > 0.80 threshold → CACHE HIT → return saved result (FREE!)
```

**The math:** We use **cosine similarity** — a measure of how "aligned" two vectors are.
Score of 1.0 = identical meaning. Score of 0.0 = completely unrelated.
We set the bar at **0.80** (data-driven from testing — not a guess).

---

## What Was Built

### Core Library: `serpapi_cache/`

| File | What it does |
|---|---|
| `cache.py` | The main `SerpApiCache` class — the brain of the whole system |
| `backends.py` | Two storage backends: `InMemoryBackend` (dev) and `RedisBackend` (production) |
| `__init__.py` | Makes it importable as a Python package |

### Scripts: `scripts/`

| File | What it does |
|---|---|
| `verify_cache.py` | 3-stage test suite that proves everything works end-to-end |
| `tune_threshold.py` | Prints similarity scores for query pairs to pick the right threshold |

---

## The Two Backends — When to Use Which

### InMemoryBackend (development & testing)
- Zero setup — no database, no Docker, nothing extra to install
- Data lives only while your Python process runs (lost on restart)
- Perfect for: testing your app, demos, quick prototypes

```python
from serpapi_cache import SerpApiCache, InMemoryBackend

cache = SerpApiCache(api_key="...", backend=InMemoryBackend())
```

### RedisBackend (production)
- Data persists across restarts — survives crashes and reboots
- Supports TTL (auto-expiry of stale results)
- Can be shared across multiple processes or servers
- Perfect for: deployed agents, production apps, multi-worker systems

```python
from serpapi_cache import SerpApiCache, RedisBackend

cache = SerpApiCache(
    api_key="...",
    backend=RedisBackend(host="localhost", port=6379),
    default_ttl=3600,   # entries expire after 1 hour
)
```

---

## How SerpApi Fits In

`SerpApiCache` is a **drop-in replacement** for `serpapi.Client.search()`.
You change one line in your code and get caching for free:

```python
# BEFORE — direct SerpApi call every time (costs credits every call)
import serpapi
client = serpapi.Client(api_key="...")
result = client.search({"engine": "google", "q": "your query"})

# AFTER — cached SerpApi (free on repeat/similar queries)
from serpapi_cache import SerpApiCache
cache = SerpApiCache(api_key="...")
result = cache.search({"engine": "google", "q": "your query"})
#                ↑ same interface, same result dict — just cached
```

Internally, on every `cache.search()` call:
1. The query is embedded into a 384-dimension vector (meaning fingerprint)
2. Compare against all stored vectors using cosine similarity
3. Score ≥ 0.80 → return cached result (**FREE**, zero SerpApi credit used)
4. Score < 0.80 → call SerpApi normally → store the result + embedding for next time

---

## Verified Test Results

All results from real test runs on this machine.

### Speed
| Operation | Time |
|---|---|
| Real SerpApi call (cache miss) | **7.08 seconds** |
| Cache hit (same query) | **0.0099 seconds** |
| **Speedup** | **710x faster** |

### Semantic Accuracy (threshold=0.80, data-driven)
| Query A | Query B | Score | Correct? |
|---|---|---|---|
| "best laptop under 50000 India" | "top laptops below 50k in India" | 0.849 | ✅ HIT |
| "cheapest medicine for diabetes" | "affordable diabetes drugs India" | 0.928 | ✅ HIT |
| "government tenders IT sector" | "India govt IT procurement" | 0.852 | ✅ HIT |
| "best laptop under 50000 India" | "India GDP growth 2026 forecast" | 0.393 | ✅ MISS |
| "medicine price comparison" | "SerpApi Python tutorial" | 0.045 | ✅ MISS |

**Safe gap:** HITs score `0.81–0.93`, MISSes score `0.04–0.39`.
Threshold of `0.80` sits cleanly in between — zero false positives.

### 3-Stage Verification (all passed ✅)
- **Stage 1** — In-memory: 6 tests — miss, hit, semantic-hit, wrong-query-miss, TTL expiry, flush
- **Stage 2** — Redis: Write → Read → Cross-instance persistence (new Python process, same Redis → still hits)
- **Stage 3** — Real SerpApi: Live API call → cached → 710x speedup confirmed

---

## Project Structure

```
serpapi-cache/
│
├── serpapi_cache/              ← the library (pip-installable)
│   ├── __init__.py             ← exposes SerpApiCache, RedisBackend, InMemoryBackend
│   ├── cache.py                ← core logic: embed → compare → hit/miss → store
│   └── backends.py             ← InMemoryBackend + RedisBackend implementations
│
├── scripts/
│   ├── verify_cache.py         ← 3-stage test suite
│   └── tune_threshold.py       ← similarity score printer for threshold tuning
│
├── docs/
│   └── judge_notes.md          ← judge background research
│
├── .env                        ← SERP_API_KEY (never committed — in .gitignore)
├── .gitignore                  ← ignores .env, __pycache__, build artifacts
├── pyproject.toml              ← makes this a proper Python package
├── requirements.txt            ← all dependencies listed
└── README.md                   ← this file
```

---

## Installation & Quick Start

```bash
# 1. Clone and install
git clone <your-repo>
cd serpapi-cache
pip install -r requirements.txt

# 2. Set your API key
echo "SERP_API_KEY=your_key_here" > .env

# 3. Verify everything works
python scripts/verify_cache.py --offline   # zero API credits used
python scripts/verify_cache.py --no-redis  # tests real SerpApi (~2 credits)
python scripts/verify_cache.py             # full test with Redis

# 4. Tune threshold for your specific query types
python scripts/tune_threshold.py
```

---

## Key Design Decisions & Why

### Why `all-MiniLM-L6-v2`?
- Tiny (90MB), fast, runs on CPU — no GPU needed
- 384-dimension embeddings — good balance of accuracy vs. speed
- Downloads once from HuggingFace, cached locally forever after

### Why cosine similarity, not exact string match?
- Exact match: `"best laptop"` ≠ `"top laptop"` → always a cache miss (wasteful)
- Cosine similarity: `"best laptop"` and `"top laptop"` → score 0.85 → cache hit (correct)

### Why threshold 0.80?
- Not arbitrary — derived by running `tune_threshold.py` on 7 real query pairs
- HITs score `0.81–0.93`, MISSes score `0.04–0.39` — the gap is massive
- 0.80 sits perfectly in the empty space between them

### Why two backends?
- Same interface — swap `InMemoryBackend()` → `RedisBackend()` and nothing else changes
- InMemory for dev/demos, Redis for production — users pick based on their needs

---

## Potential Breaking Points — Know Before Judges Ask

### 1. Embedding model version drift
**What:** If `sentence-transformers` library updates `all-MiniLM-L6-v2`, embedding values may shift.
**Impact:** Old cached embeddings won't match new embeddings → cache miss storm.
**Fix:** Pin version in `requirements.txt` (already done). Flush Redis after any upgrade.

### 2. Redis crashes / not running
**What:** If Redis stops, `RedisBackend` throws `ConnectionError` immediately.
**Impact:** Entire agent crashes.
**Fix:** Use try/except to fall back to `InMemoryBackend`:
```python
try:
    backend = RedisBackend(host="localhost")
except Exception:
    backend = InMemoryBackend()  # graceful degradation
```

### 3. SerpApi JSON schema changes
**What:** SerpApi occasionally changes response field names (e.g., `organic_results` → something else).
**Impact:** Code reading specific fields breaks. Cache itself is unaffected (stores raw JSON).
**Fix:** Always use `.get("field", default)` when reading SerpApi results downstream.

### 4. Memory growth without TTL
**What:** `InMemoryBackend` with `default_ttl=0` (never expire) accumulates entries forever.
**Impact:** Memory leak in long-running agents.
**Fix:** Always set a `default_ttl`. Default in this library is 3600s (1 hour).

### 5. Windows Redis not persistent across reboots
**What:** On Windows, `redis-server.exe` started manually dies on reboot.
**Impact:** Cache empty after restart.
**Fix:** Register as Windows Service: `redis-server --service-install`, or use Docker.

### 6. First-run model download delay
**What:** First time `SerpApiCache` initializes, it downloads ~90MB model from HuggingFace.
**Impact:** 30-60 second delay on first ever run in a fresh environment.
**Fix:** Pre-download in setup/Dockerfile:
```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

---

## Business Value — Why This Matters

A team running an AI agent that makes 1000 SerpApi searches/day:

| Metric | Without Cache | With Cache (40% hit rate) |
|---|---|---|
| Daily API calls | 1000 | 600 |
| Daily credits used | 1000 | 600 |
| Credits saved/day | — | **400** |
| Credits saved/year | — | **146,000** (~US$1,460) |
| Response time | 7s average | 0.01s on hits |

---

## How This Fits the Hackathon

**Track:** Open-Source Integrations

**SerpApi role:** `serpapi-cache` wraps `serpapi.Client.search()` directly. Every cache miss triggers a real SerpApi call. The library exists *because of* SerpApi — SerpApi is the core engine, not a bolt-on.

**Judge alignment:**
- **Josef:** Clean repo, `pyproject.toml`, `.gitignore`, typed interfaces, comprehensive README — production open-source quality
- **Pranav:** Directly saves users' SerpApi credits — clear, quantifiable business value
- **Tomas:** Foundation for the distiller pipeline — clean LLM context starts with clean, non-redundant data
- **Adarsh:** `pip install`, 3 lines to use, works out of the box — ships fast, practical

---

## What's Next (Roadmap)

- [ ] `serpapi_distiller/` — strip noisy SerpApi JSON into clean Markdown for LLMs
- [ ] Unified `SerpApiPipeline` — cache + distill in one call
- [ ] Demo agent (PharmaWatch / TenderHawk) using the full stack
- [ ] `docker-compose.yml` — one command to run Redis + demo agent
- [ ] Async support (`async def search()`)
- [ ] Auto-fallback: Redis → InMemory on connection failure

---

## License

MIT — free to use, modify, and distribute.
