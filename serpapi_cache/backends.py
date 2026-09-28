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
import sys
import time
from abc import ABC, abstractmethod
from typing import Any, Optional


def say(message: str = "") -> None:
    """
    print() that never raises: on a console or redirected log whose encoding can't show emoji
    (Windows cp1252), characters are replaced. A raising print inside RedisBackend.__init__ would
    otherwise be read as "Redis unreachable" and silently switch the cache to passthrough.
    """
    try:
        print(message)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        print(message.encode(encoding, errors="replace").decode(encoding, errors="replace"))


# ─────────────────────────────────────────────
# Base
# ─────────────────────────────────────────────

class BaseBackend(ABC):
    """
    Abstract cache backend. Stores (value, embedding, query_text, params_sig) keyed by hash.
    get_all() records carry params_sig (None if stored without one): semantic hits require a match.
    """

    @abstractmethod
    def set(self, key: str, value: Any, embedding: list[float], ttl: int, query_text: str = "",
            params_sig: str = "") -> None: ...

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

    Each entry is stored as four Redis keys:
      - serpapi:cache:<hash>:value     → JSON-serialized API result
      - serpapi:cache:<hash>:embedding → JSON-serialized float list
      - serpapi:cache:<hash>:query     → original query text (for dosage guard)
      - serpapi:cache:<hash>:params    → signature of the non-query params (semantic hits need a match)

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
        say(f"✅ Redis connected at {host}:{port} (db={db})")

    def _val_key(self, key: str) -> str:
        return f"{self.PREFIX}{key}:value"

    def _emb_key(self, key: str) -> str:
        return f"{self.PREFIX}{key}:embedding"

    def _qry_key(self, key: str) -> str:
        return f"{self.PREFIX}{key}:query"

    def _sig_key(self, key: str) -> str:
        return f"{self.PREFIX}{key}:params"

    def set(self, key: str, value: Any, embedding: list[float], ttl: int, query_text: str = "",
            params_sig: str = "") -> None:
        pipe = self._r.pipeline()
        pipe.set(self._val_key(key), json.dumps(value))
        pipe.set(self._emb_key(key), json.dumps(embedding))
        pipe.set(self._qry_key(key), query_text)
        pipe.set(self._sig_key(key), params_sig)
        if ttl > 0:
            pipe.expire(self._val_key(key), ttl)
            pipe.expire(self._emb_key(key), ttl)
            pipe.expire(self._qry_key(key), ttl)
            pipe.expire(self._sig_key(key), ttl)
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
                "params_sig": self._r.get(self._sig_key(key)) or None,
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
        pipe.delete(self._sig_key(key))
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
                pipe.delete(self._sig_key(key))
            pipe.delete(self.INDEX_KEY)
            pipe.execute()

    def size(self) -> int:
        return len(self.get_all())
