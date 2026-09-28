"""
cache.py — Core SerpApiCache class.

Flow on every search():
  0. Exact match: same params (query normalized: case, spaces, '500 mg'→'500mg') seen
     before → return straight from Redis (no embedding)
  1. Encode the query into a vector embedding
  2. Compare against all cached embeddings via cosine similarity
  3. Run dosage guard: if both queries contain numbers and the sets differ → force MISS
  4. If similarity >= threshold AND dosage guard passes → return cached result (CACHE HIT)
  5. If below threshold or guard fires → call SerpApi → store result + embedding (CACHE MISS)
     The store runs on a background writer thread, so the caller gets the result without
     waiting for Redis. wait_for_writes() blocks until pending stores land (also runs at exit).

search() is thread-safe: parallel searches share the embedding model behind a lock.

If Redis is unavailable at startup, the cache runs in passthrough mode:
  every search() call hits SerpApi directly — no caching, no crash.

Start Redis with: docker compose up -d
"""

import hashlib
import json
import os
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from typing import Any, Callable, Optional

from .backends import BaseBackend, RedisBackend, say


# ─────────────────────────────────────────────
# Call log tags — say *why* a search happened
# ─────────────────────────────────────────────

_context = threading.local()


@contextmanager
def call_tag(tag: str):
    """Label every search() made on this thread inside the block, e.g. 'direct link: 1mg'."""
    previous = getattr(_context, "tag", None)
    _context.tag = tag
    try:
        yield
    finally:
        _context.tag = previous


# ─────────────────────────────────────────────
# Cosine similarity (pure numpy — no heavy deps)
# ─────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    import numpy as np
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom else 0.0


# ─────────────────────────────────────────────
# Dosage guard
# ─────────────────────────────────────────────

def _extract_numbers(text: str) -> set[str]:
    """Extract all numeric tokens (integers and decimals) from a string."""
    return set(re.findall(r"\d+\.?\d*", text))


def _dosage_guard_fires(query_a: str, query_b: str) -> bool:
    """
    Returns True (block the hit) if both queries contain numeric tokens
    and those sets differ — e.g. 'Metformin 20mg' vs 'Metformin 200mg'.
    If either query has no numbers, the guard is skipped (returns False).
    """
    nums_a = _extract_numbers(query_a)
    nums_b = _extract_numbers(query_b)
    if not nums_a or not nums_b:
        return False  # no dosage in at least one query — let cosine decide
    return nums_a != nums_b


# ─────────────────────────────────────────────
# Query normalization
# ─────────────────────────────────────────────

_UNIT_SPACING = re.compile(r"(\d+(?:\.\d+)?)\s+(mg|mcg|g|ml|iu|%)\b", re.IGNORECASE)


def _normalize_q(q: str) -> str:
    """'Dolo  650 MG price' → 'dolo 650mg price' — lowercase, single spaces, units glued to numbers."""
    q = " ".join(str(q).lower().split())
    return _UNIT_SPACING.sub(r"\1\2", q)


def _cache_params(params: dict) -> dict:
    """Params as the cache sees them (key + embedding). SerpApi still gets the originals."""
    if "q" not in params:
        return params
    return {**params, "q": _normalize_q(params["q"])}


def _params_signature(params: dict) -> str:
    """
    Hash of every param except the query text. The embedding only sees q, engine, location and
    country, so without this a semantic hit could hand back a result fetched with a different page
    (start), filter (tbs), language (hl) or json_restrictor. A semantic hit needs the same signature.
    """
    rest = {k: v for k, v in params.items() if k not in ("q", "api_key")}
    return hashlib.sha256(json.dumps(rest, sort_keys=True).encode()).hexdigest()[:16]


# ─────────────────────────────────────────────
# Main Cache Class
# ─────────────────────────────────────────────

class SerpApiCache:
    """
    Semantic cache wrapper around the SerpApi Python client.
    Uses Redis as the only backend — persistent across restarts.

    Args:
        api_key              : SerpApi API key (or set SERP_API_KEY in .env)
        backend              : RedisBackend instance (auto-connects to localhost:6379 if not passed)
        similarity_threshold : Cosine similarity cutoff for a cache hit (0–1)
        default_ttl          : Seconds before a cached entry expires (0 = never)
        embedding_model      : Sentence-Transformers model name
        verbose              : Print HIT/MISS logs

    Example:
        from serpapi_cache import SerpApiCache, RedisBackend

        cache = SerpApiCache(
            api_key="...",
            backend=RedisBackend(host="localhost"),
            similarity_threshold=0.88,
        )
        results = cache.search({"engine": "google", "q": "Metformin 500mg price India"})
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        backend: Optional[BaseBackend] = None,
        similarity_threshold: float = 0.80,
        default_ttl: int = 3600,          # 1 hour default
        embedding_model: str = "all-MiniLM-L6-v2",
        verbose: bool = True,
    ):
        # ── API key ──────────────────────────────────────────────
        self.api_key = api_key or os.getenv("SERP_API_KEY") or os.getenv("SERPAPI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "No SerpApi key found. Pass api_key= or set SERP_API_KEY in your .env"
            )

        # ── Config ───────────────────────────────────────────────
        self.threshold = similarity_threshold
        self.default_ttl = default_ttl
        self.verbose = verbose

        # ── Backend — Redis with passthrough fallback ────────────
        if backend is not None:
            # Caller passed an explicit backend — use it, let errors propagate
            self.backend: Optional[BaseBackend] = backend
        else:
            try:
                self.backend = RedisBackend(host="localhost", port=6379)
            except Exception as e:
                import warnings
                warnings.warn(
                    f"\n⚠️  Redis not reachable (localhost:6379): {e}\n"
                    "   Running in PASSTHROUGH mode — all searches go directly to SerpApi.\n"
                    "   Start Redis: docker compose up -d",
                    stacklevel=2,
                )
                self.backend = None

        # ── Embedding model (lazy-loaded on first use) ────────────
        self._model_name = embedding_model
        self._model = None  # loaded lazily
        self._model_lock = threading.Lock()

        # ── Background Redis writer ──────────────────────────────
        # One thread keeps writes ordered; pending writes finish at interpreter exit.
        self._writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="serpapi-cache-writer")
        self._pending_writes: set[Future] = set()
        self._pending_lock = threading.Lock()

        # ── Stats ─────────────────────────────────────────────────
        self.stats = {"hits": 0, "exact_hits": 0, "misses": 0, "api_calls_saved": 0}
        self.call_log: list[dict] = []
        self._log_lock = threading.Lock()

    # ─────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────

    def search(self, params: dict, ttl: Optional[int] = None, exact_only: bool = False,
               ttl_for: Optional[Callable[[dict], Optional[int]]] = None) -> dict:
        """
        Drop-in replacement for serpapi.Client.search().
        Returns cached result if a semantically similar query exists
        and the dosage guard does not block the match.

        exact_only=True skips the similarity lookup: only the identical (normalized) query
        can hit. Use it for exact product names — 'Calpol 650' must never be served
        'Dolo 650'. The result is still stored with its embedding for later reuse.

        ttl_for(result) can shorten how long a fresh API result is kept: it returns a TTL in
        seconds, or None for the normal one. Use it for results that look wrong (e.g. a search
        that returned none of the product asked for), so a bad response doesn't stick for a day.

        If Redis is unavailable (backend is None), skips cache entirely
        and calls SerpApi directly — passthrough mode.

        Every call is recorded in the call log (see pop_call_log()).
        """
        started = time.perf_counter()
        outcome, result = self._search(params, ttl, exact_only, ttl_for)
        entry = {
            "start": started,
            "end": time.perf_counter(),
            "engine": params.get("engine", ""),
            "query": params.get("q") or f"page_token …{str(params.get('page_token', ''))[-10:]}",
            "outcome": outcome,
            "credit": outcome.startswith("api_call"),
            "tag": getattr(_context, "tag", None),
        }
        with self._log_lock:
            self.call_log.append(entry)
        return result

    def pop_call_log(self) -> list[dict]:
        """Return and clear the call log: start/end (perf_counter), engine, query, outcome, credit, tag."""
        with self._log_lock:
            log, self.call_log = self.call_log, []
        return log

    def _search(self, params: dict, ttl: Optional[int], exact_only: bool,
                ttl_for: Optional[Callable[[dict], Optional[int]]] = None) -> tuple[str, dict]:
        # Passthrough mode — Redis unavailable
        if self.backend is None:
            if self.verbose:
                query_text = self._params_to_query_string(params)
                say(f"⚡ PASSTHROUGH | Redis down — calling SerpApi directly for '{query_text[:60]}'")
            self.stats["misses"] += 1
            return "api_call (passthrough)", self._call_serpapi(params)

        # Read-your-writes: a store still in flight (a few ms) lands before this lookup,
        # so a repeat query always hits. Only the search that made the API call skips waiting.
        self.wait_for_writes()

        key_params = _cache_params(params)
        query_text = self._params_to_query_string(key_params)
        cache_key = self._make_key(key_params)
        params_sig = _params_signature(key_params)

        # 0. Exact match — identical params were asked before. One Redis GET,
        #    no embedding, no similarity scan.
        exact_hit = self.backend.get_by_key(cache_key)
        if exact_hit is not None:
            self.stats["hits"] += 1
            self.stats["exact_hits"] += 1
            self.stats["api_calls_saved"] += 1
            if self.verbose:
                say(f"🟢 CACHE HIT (EXACT) | query='{query_text[:60]}'")
            return "exact_hit", exact_hit

        # Token-only requests (e.g. google_immersive_product with page_token → the
        # final product link) have no text to compare: every one would read
        # 'engine:google_immersive_product' and match the first product cached.
        # Like the dosage guard, a different token must always call SerpApi,
        # so they are exact-match only.
        is_text_query = "q" in params
        use_semantic = is_text_query and not exact_only
        embedding = self._embed(query_text) if use_semantic else None  # exact_only: embed at store time

        # 1. Check for semantic match in cache
        best_match = self._find_best_match(embedding, query_text, params_sig) if use_semantic else None

        if best_match:
            similarity, matched_key = best_match
            cached_result = self.backend.get_by_key(matched_key)
            if cached_result:
                self.stats["hits"] += 1
                self.stats["api_calls_saved"] += 1
                if self.verbose:
                    say(f"🟢 CACHE HIT  | similarity={similarity:.3f} | query='{query_text[:60]}'")
                return f"semantic_hit ({similarity:.3f})", cached_result

        # 2. Cache miss — call SerpApi
        self.stats["misses"] += 1
        if self.verbose:
            say(f"🔴 CACHE MISS | query='{query_text[:60]}' → calling SerpApi...")

        result = self._call_serpapi(params)

        # 3. Store result + embedding + query_text — in the background
        effective_ttl = ttl if ttl is not None else self.default_ttl
        if ttl_for is not None:
            try:
                override = ttl_for(result)
            except Exception as e:  # a failing check never costs the result or the store
                override = None
                say(f"⚠️  ttl_for failed for '{query_text[:60]}': {e}")
            if override is not None:
                effective_ttl = override
                if self.verbose:
                    say(f"⏱️  SHORT TTL {override}s | query='{query_text[:60]}'")
        self._store_async(cache_key, result, embedding, effective_ttl, query_text, is_text_query, params_sig)

        return "api_call", result

    def wait_for_writes(self, timeout: Optional[float] = None) -> None:
        """Block until every background Redis store has finished."""
        with self._pending_lock:
            pending = set(self._pending_writes)
        wait(pending, timeout=timeout)

    def warm_up(self) -> float:
        """
        Load the embedding model and run one dummy encode now, at startup, so the
        first real search doesn't pay the model-loading delay. Returns elapsed ms.
        """
        import time
        t0 = time.perf_counter()
        self._load_model()
        self._model.encode("warm up", normalize_embeddings=True)
        return (time.perf_counter() - t0) * 1000

    def flush(self) -> None:
        """Clear all cached entries. No-op if Redis is unavailable."""
        if self.backend is None:
            return
        self.wait_for_writes()
        self.backend.flush()
        if self.verbose:
            say("🗑️  Cache flushed.")

    def size(self) -> int:
        """Number of entries currently in cache. Returns 0 if Redis is unavailable."""
        if self.backend is None:
            return 0
        return self.backend.size()

    def get_stats(self) -> dict:
        """Return hit/miss statistics."""
        total = self.stats["hits"] + self.stats["misses"]
        hit_rate = (self.stats["hits"] / total * 100) if total else 0
        return {
            **self.stats,
            "total_searches": total,
            "hit_rate_pct": round(hit_rate, 1),
            "cache_size": self.size(),
            "backend": "passthrough" if self.backend is None else "redis",
        }

    def print_stats(self) -> None:
        s = self.get_stats()
        say("\n" + "─" * 45)
        say(f"  📊 SerpApi Cache Statistics")
        say("─" * 45)
        say(f"  Total searches   : {s['total_searches']}")
        say(f"  Cache hits       : {s['hits']}  ✅  (exact: {s['exact_hits']})")
        say(f"  Cache misses     : {s['misses']}  ❌")
        say(f"  Hit rate         : {s['hit_rate_pct']}%")
        say(f"  API calls saved  : {s['api_calls_saved']}")
        say(f"  Entries in cache : {s['cache_size']}")
        say("─" * 45 + "\n")

    # ─────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────

    def _store_async(self, key: str, result: dict, embedding: Optional[list[float]],
                     ttl: int, query_text: str, is_text_query: bool, params_sig: str = "") -> None:
        if embedding is None and is_text_query:
            # Load the model here, not on the writer: a first-time import during interpreter
            # shutdown fails and the write is lost. No-op after warm_up().
            self._load_model()

        def store():
            try:
                vector = embedding if embedding is not None else (self._embed(query_text) if is_text_query else [])
                self.backend.set(key, result, vector, ttl, query_text, params_sig=params_sig)
            except Exception as e:  # a failed store only costs a future cache hit
                say(f"⚠️  Cache store failed for '{query_text[:60]}': {e}")

        future = self._writer.submit(store)
        with self._pending_lock:
            self._pending_writes.add(future)
        future.add_done_callback(self._forget_write)

    def _forget_write(self, future: Future) -> None:
        with self._pending_lock:
            self._pending_writes.discard(future)

    def _load_model(self) -> None:
        with self._model_lock:
            if self._model is None:
                if self.verbose:
                    say(f"⏳ Loading embedding model '{self._model_name}' (first-time only)...")
                # Windows: scikit-learn's OpenMP runtime (vcomp140) takes ~20s to load once torch's
                # is loaded, which is the order sentence_transformers imports them in. Loading
                # scikit-learn first takes ~1.5s.
                try:
                    import sklearn.utils._openmp_helpers  # noqa: F401
                except ImportError:
                    pass
                from sentence_transformers import SentenceTransformer
                try:
                    # Local copy first: skips ~7s of HuggingFace update checks on every start.
                    self._model = SentenceTransformer(self._model_name, local_files_only=True)
                except Exception:
                    self._model = SentenceTransformer(self._model_name)  # not downloaded yet
                if self.verbose:
                    say("✅ Embedding model loaded.\n")

    def _embed(self, text: str) -> list[float]:
        """Encode text into a float vector using Sentence-Transformers. Safe across threads."""
        self._load_model()
        with self._model_lock:
            return self._model.encode(text, normalize_embeddings=True).tolist()

    def _find_best_match(self, query_embedding: list[float], query_text: str,
                         params_sig: str) -> Optional[tuple[float, str]]:
        """
        Compare query embedding against cached embeddings fetched with the same other params
        (params_sig). Entries stored without a signature are never semantic candidates.
        Applies dosage guard after finding the best cosine candidate.
        Returns (similarity_score, cache_key) if above threshold and guard passes, else None.
        """
        records = self.backend.get_all()
        if not records:
            return None

        best_score = -1.0
        best_key = None
        best_query_text = ""

        for record in records:
            if not record["embedding"]:
                continue  # token-only entry (product link) — exact-match only
            if record.get("params_sig") != params_sig:
                continue  # different page / filter / language / json_restrictor, or unknown
            score = _cosine_similarity(query_embedding, record["embedding"])
            if score > best_score:
                best_score = score
                best_key = record["key"]
                best_query_text = record.get("query_text", "")

        if best_score < self.threshold:
            return None

        # Dosage guard — check after threshold to avoid unnecessary work
        if _dosage_guard_fires(query_text, best_query_text):
            if self.verbose:
                say(f"⚠️  DOSAGE GUARD | blocked hit | '{query_text[:40]}' vs '{best_query_text[:40]}'")
            return None

        return (best_score, best_key)

    def _call_serpapi(self, params: dict) -> dict:
        """Make the actual SerpApi call. Times out after SERPAPI_TIMEOUT seconds (default 30)."""
        try:
            import serpapi
        except ImportError:
            raise ImportError("serpapi package not installed. Run: pip install serpapi")

        # The client's default is no timeout: one hung request would block its search forever.
        client = serpapi.Client(api_key=self.api_key, timeout=float(os.getenv("SERPAPI_TIMEOUT", "30")))
        result = client.search({**params})
        return dict(result)

    @staticmethod
    def _params_to_query_string(params: dict) -> str:
        """Convert search params to a single string for embedding."""
        parts = []
        if "q" in params:
            parts.append(params["q"])
        if "engine" in params:
            parts.append(f"engine:{params['engine']}")
        if "location" in params:
            parts.append(f"location:{params['location']}")
        if "gl" in params:
            parts.append(f"country:{params['gl']}")
        return " | ".join(parts) if parts else json.dumps(params, sort_keys=True)

    @staticmethod
    def _make_key(params: dict) -> str:
        """Deterministic hash key for exact param match storage."""
        canonical = json.dumps(params, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]
