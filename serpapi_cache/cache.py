"""
cache.py — Core SerpApiCache class.

Flow on every search():
  1. Encode the query into a vector embedding
  2. Compare against all cached embeddings via cosine similarity
  3. Run dosage guard: if both queries contain numbers and the sets differ → force MISS
  4. If similarity >= threshold AND dosage guard passes → return cached result (CACHE HIT)
  5. If below threshold or guard fires → call SerpApi → store result + embedding (CACHE MISS)

Requires Redis. Start with: docker compose up -d
"""

import hashlib
import json
import os
import re
from typing import Any, Optional

from .backends import BaseBackend, RedisBackend


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

        # ── Backend — Redis only ─────────────────────────────────
        if backend is not None:
            self.backend: BaseBackend = backend
        else:
            self.backend = RedisBackend(host="localhost", port=6379)

        # ── Embedding model (lazy-loaded on first use) ────────────
        self._model_name = embedding_model
        self._model = None  # loaded lazily

        # ── Stats ─────────────────────────────────────────────────
        self.stats = {"hits": 0, "misses": 0, "api_calls_saved": 0}

    # ─────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────

    def search(self, params: dict, ttl: Optional[int] = None) -> dict:
        """
        Drop-in replacement for serpapi.Client.search().
        Returns cached result if a semantically similar query exists
        and the dosage guard does not block the match.
        """
        query_text = self._params_to_query_string(params)
        embedding = self._embed(query_text)
        cache_key = self._make_key(params)

        # 1. Check for semantic match in cache
        best_match = self._find_best_match(embedding, query_text)

        if best_match:
            similarity, matched_key = best_match
            cached_result = self.backend.get_by_key(matched_key)
            if cached_result:
                self.stats["hits"] += 1
                self.stats["api_calls_saved"] += 1
                if self.verbose:
                    print(f"🟢 CACHE HIT  | similarity={similarity:.3f} | query='{query_text[:60]}'")
                return cached_result

        # 2. Cache miss — call SerpApi
        self.stats["misses"] += 1
        if self.verbose:
            print(f"🔴 CACHE MISS | query='{query_text[:60]}' → calling SerpApi...")

        result = self._call_serpapi(params)

        # 3. Store result + embedding + query_text
        effective_ttl = ttl if ttl is not None else self.default_ttl
        self.backend.set(cache_key, result, embedding, effective_ttl, query_text)

        return result

    def flush(self) -> None:
        """Clear all cached entries."""
        self.backend.flush()
        if self.verbose:
            print("🗑️  Cache flushed.")

    def size(self) -> int:
        """Number of entries currently in cache."""
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
        }

    def print_stats(self) -> None:
        s = self.get_stats()
        print("\n" + "─" * 45)
        print(f"  📊 SerpApi Cache Statistics")
        print("─" * 45)
        print(f"  Total searches   : {s['total_searches']}")
        print(f"  Cache hits       : {s['hits']}  ✅")
        print(f"  Cache misses     : {s['misses']}  ❌")
        print(f"  Hit rate         : {s['hit_rate_pct']}%")
        print(f"  API calls saved  : {s['api_calls_saved']}")
        print(f"  Entries in cache : {s['cache_size']}")
        print("─" * 45 + "\n")

    # ─────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────

    def _embed(self, text: str) -> list[float]:
        """Encode text into a float vector using Sentence-Transformers."""
        if self._model is None:
            if self.verbose:
                print(f"⏳ Loading embedding model '{self._model_name}' (first-time only)...")
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
            if self.verbose:
                print("✅ Embedding model loaded.\n")
        return self._model.encode(text, normalize_embeddings=True).tolist()

    def _find_best_match(self, query_embedding: list[float], query_text: str) -> Optional[tuple[float, str]]:
        """
        Compare query embedding against all cached embeddings.
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
                print(f"⚠️  DOSAGE GUARD | blocked hit | '{query_text[:40]}' vs '{best_query_text[:40]}'")
            return None

        return (best_score, best_key)

    def _call_serpapi(self, params: dict) -> dict:
        """Make the actual SerpApi call."""
        try:
            import serpapi
        except ImportError:
            raise ImportError("serpapi package not installed. Run: pip install serpapi")

        client = serpapi.Client(api_key=self.api_key)
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
