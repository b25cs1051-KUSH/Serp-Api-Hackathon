"""
backends.py — Redis storage backend for the SerpApi semantic cache.

RedisBackend is the only supported backend. It provides:
  - Persistence across restarts (AOF via docker-compose)
  - Native TTL support
  - Cross-process cache sharing

Start Redis before using:
    docker compose up -d
"""

import json
import time
from abc import ABC, abstractmethod
from typing import Any, Optional


# ─────────────────────────────────────────────
# Base
# ─────────────────────────────────────────────

class BaseBackend(ABC):
    """Abstract cache backend. Stores (value, embedding, query_text) pairs keyed by hash."""

    @abstractmethod
    def set(self, key: str, value: Any, embedding: list[float], ttl: int, query_text: str = "") -> None: ...

    @abstractmethod
    def get_all(self) -> list[dict]: ...

    @abstractmethod
    def get_by_key(self, key: str) -> Optional[Any]: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def flush(self) -> None: ...

    @abstractmethod
    def size(self) -> int: ...


# ─────────────────────────────────────────────
# Redis Backend (only backend)
# ─────────────────────────────────────────────

class RedisBackend(BaseBackend):
    """
    Redis-backed cache. Persistent across restarts, supports TTL natively.

    Each entry is stored as three Redis keys:
      - serpapi:cache:<hash>:value     → JSON-serialized API result
      - serpapi:cache:<hash>:embedding → JSON-serialized float list
      - serpapi:cache:<hash>:query     → original query text (for dosage guard)

    An index key `serpapi:cache:index` (Redis Set) tracks all active hashes
    so we can retrieve all embeddings for similarity comparison.

    Start Redis:
        docker compose up -d
    """

    INDEX_KEY = "serpapi:cache:index"
    PREFIX = "serpapi:cache:"

    def __init__(self, host: str = "localhost", port: int = 6379,
                 db: int = 0, password: Optional[str] = None):
        try:
            import redis
        except ImportError:
            raise ImportError(
                "Redis package not installed. Run: pip install redis"
            )
        self._r = redis.Redis(
            host=host, port=port, db=db,
            password=password, decode_responses=True
        )
        # Test connection immediately — fail fast
        self._r.ping()
        print(f"✅ Redis connected at {host}:{port} (db={db})")

    def _val_key(self, key: str) -> str:
        return f"{self.PREFIX}{key}:value"

    def _emb_key(self, key: str) -> str:
        return f"{self.PREFIX}{key}:embedding"

    def _qry_key(self, key: str) -> str:
        return f"{self.PREFIX}{key}:query"

    def set(self, key: str, value: Any, embedding: list[float], ttl: int, query_text: str = "") -> None:
        pipe = self._r.pipeline()
        pipe.set(self._val_key(key), json.dumps(value))
        pipe.set(self._emb_key(key), json.dumps(embedding))
        pipe.set(self._qry_key(key), query_text)
        if ttl > 0:
            pipe.expire(self._val_key(key), ttl)
            pipe.expire(self._emb_key(key), ttl)
            pipe.expire(self._qry_key(key), ttl)
        pipe.sadd(self.INDEX_KEY, key)
        pipe.execute()

    def get_all(self) -> list[dict]:
        keys = self._r.smembers(self.INDEX_KEY)
        records = []
        dead_keys = []
        for key in keys:
            val = self._r.get(self._val_key(key))
            emb = self._r.get(self._emb_key(key))
            if val is None or emb is None:
                # TTL expired — clean up index
                dead_keys.append(key)
                continue
            records.append({
                "key": key,
                "value": json.loads(val),
                "embedding": json.loads(emb),
                "query_text": self._r.get(self._qry_key(key)) or "",
            })
        if dead_keys:
            self._r.srem(self.INDEX_KEY, *dead_keys)
        return records

    def get_by_key(self, key: str) -> Optional[Any]:
        val = self._r.get(self._val_key(key))
        return json.loads(val) if val else None

    def delete(self, key: str) -> None:
        pipe = self._r.pipeline()
        pipe.delete(self._val_key(key))
        pipe.delete(self._emb_key(key))
        pipe.delete(self._qry_key(key))
        pipe.srem(self.INDEX_KEY, key)
        pipe.execute()

    def flush(self) -> None:
        keys = self._r.smembers(self.INDEX_KEY)
        if keys:
            pipe = self._r.pipeline()
            for key in keys:
                pipe.delete(self._val_key(key))
                pipe.delete(self._emb_key(key))
                pipe.delete(self._qry_key(key))
            pipe.delete(self.INDEX_KEY)
            pipe.execute()

    def size(self) -> int:
        return len(self.get_all())
