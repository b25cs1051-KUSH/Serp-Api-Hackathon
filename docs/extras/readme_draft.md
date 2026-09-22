
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






## How This Fits the Hackathon

**Track:** Open-Source Integrations

**SerpApi role:** `serpapi-cache` wraps `serpapi.Client.search()` directly. Every cache miss triggers a real SerpApi call. The library exists *because of* SerpApi — SerpApi is the core engine, not a bolt-on.

**Judge alignment:**
- **Josef:** Clean repo, `pyproject.toml`, `.gitignore`, typed interfaces, comprehensive README — production open-source quality
- **Pranav:** Directly saves users' SerpApi credits — clear, quantifiable business value
- **Tomas:** Foundation for the distiller pipeline — clean LLM context starts with clean, non-redundant data
- **Adarsh:** `pip install`, 3 lines to use, works out of the box — ships fast, practical
