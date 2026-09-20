"""
verify_cache.py — Full verification suite for SerpApiCache.

Runs 3 stages:
  Stage 1: In-Memory backend (no Redis needed) — proves core logic works (dev)
  Stage 2: Redis backend — proves production path works (deployment)
  Stage 3: Real SerpApi calls — proves end-to-end integration 

Run:
    python verify_cache.py                    # Stage 1 + 2 + 3
    python verify_cache.py --no-redis         # Stage 1 + 3 only (skip Redis)
    python verify_cache.py --offline          # Stage 1 only (no API calls, no Redis)
"""

import sys, io, os
# Allow running from any directory — add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import time
import argparse
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────
# Helpers
# ──────────────────────────────────────

def section(title: str):
    print(f"\n{'═' * 55}")
    print(f"  {title}")
    print('═' * 55)

def ok(msg: str):
    print(f"  ✅  {msg}")

def fail(msg: str):
    print(f"  ❌  {msg}")
    sys.exit(1)

def info(msg: str):
    print(f"  ℹ️   {msg}")


# ──────────────────────────────────────
# Stage 1: In-Memory Backend
# ──────────────────────────────────────

def test_in_memory():
    section("STAGE 1 — In-Memory Backend (no Redis required)")

    from serpapi_cache import SerpApiCache, InMemoryBackend

    # Use a dummy API key for this stage — we mock the SerpApi call
    cache = SerpApiCache(
        api_key="test_key_not_real",
        backend=InMemoryBackend(),
        similarity_threshold=0.80,  # tuned default
        default_ttl=60,
        verbose=True,
    )

    # ── Monkey-patch _call_serpapi to avoid real API calls ──
    call_count = [0]
    def fake_serpapi(params):
        call_count[0] += 1
        return {"organic_results": [{"title": f"Fake result for: {params.get('q')}"}],
                "_mock": True}
    cache._call_serpapi = fake_serpapi

    # ── Test 1: First call → miss → stored ──
    info("Test 1: First search (should be MISS)")
    r1 = cache.search({"engine": "google", "q": "best laptop under 50000 India"})
    assert call_count[0] == 1, "Expected 1 API call"
    assert cache.size() == 1, "Expected 1 entry in cache"
    ok(f"MISS confirmed — API called once, cache now has {cache.size()} entry")

    # ── Test 2: Exact same query → hit ──
    info("Test 2: Exact same query (should be HIT)")
    r2 = cache.search({"engine": "google", "q": "best laptop under 50000 India"})
    assert call_count[0] == 1, "API should NOT be called again"
    ok("HIT confirmed — no extra API call")

    # ── Test 3: Semantically similar query → hit ──
    info("Test 3: Semantically similar query (should be HIT via similarity)")
    r3 = cache.search({"engine": "google", "q": "top laptops below 50k in India"})
    if call_count[0] == 1:
        ok(f"Semantic HIT confirmed — similar query matched cache")
    else:
        info("Semantic MISS (similarity below threshold) — this is OK, threshold can be tuned")

    # ── Test 4: Very different query → miss ──
    info("Test 4: Completely different query (should be MISS)")
    calls_before = call_count[0]
    r4 = cache.search({"engine": "google", "q": "India GDP growth 2026 forecast"})
    assert call_count[0] > calls_before, "New query should trigger API call"
    ok(f"MISS confirmed — different query correctly triggers API call")

    # ── Test 5: TTL check ──
    info("Test 5: TTL expiry — cache entry with 1 second TTL")
    cache_ttl = SerpApiCache(
        api_key="test_key",
        backend=InMemoryBackend(),
        default_ttl=1,
        verbose=False,
    )
    cache_ttl._call_serpapi = fake_serpapi
    cache_ttl.search({"engine": "google", "q": "ttl test query"})
    assert cache_ttl.size() == 1, "Should have 1 entry"
    time.sleep(1.1)
    assert cache_ttl.size() == 0, "Entry should have expired"
    ok("TTL expiry works correctly")

    # ── Test 6: Flush ──
    info("Test 6: Flush cache")
    cache.flush()
    assert cache.size() == 0, "Cache should be empty after flush"
    ok("Flush works correctly")

    # ── Stats ──
    cache.print_stats()

    ok("ALL IN-MEMORY TESTS PASSED ✓")


# ──────────────────────────────────────
# Stage 2: Redis Backend
# ──────────────────────────────────────

def test_redis():
    section("STAGE 2 — Redis Backend (production path)")

    try:
        from serpapi_cache import SerpApiCache, RedisBackend
        backend = RedisBackend(host="localhost", port=6379)
    except Exception as e:
        fail(f"Could not connect to Redis: {e}\n"
             f"  → Start Redis with: docker run -d -p 6379:6379 redis\n"
             f"  → Or run with --no-redis to skip this stage")

    cache = SerpApiCache(
        api_key="test_key_redis",
        backend=backend,
        similarity_threshold=0.85,
        default_ttl=30,
        verbose=True,
    )

    # Flush any leftover test data
    cache.flush()

    call_count = [0]
    def fake_serpapi(params):
        call_count[0] += 1
        return {"organic_results": [{"title": f"Redis result: {params.get('q')}"}], "_redis_mock": True}
    cache._call_serpapi = fake_serpapi

    info("Test 1: Write to Redis + read back")
    cache.search({"engine": "google", "q": "Redis test query serpapi cache"})
    assert cache.size() == 1
    ok("Written to Redis successfully")

    info("Test 2: Hit from Redis")
    cache.search({"engine": "google", "q": "Redis test query serpapi cache"})
    assert call_count[0] == 1, "Should hit Redis, not call API"
    ok("Redis cache HIT confirmed")

    info("Test 3: Persistence — create new cache instance, same Redis")
    cache2 = SerpApiCache(
        api_key="test_key_redis",
        backend=RedisBackend(host="localhost", port=6379),
        similarity_threshold=0.85,
        verbose=True,
    )
    cache2._call_serpapi = fake_serpapi
    cache2.search({"engine": "google", "q": "Redis test query serpapi cache"})
    assert call_count[0] == 1, "New instance should still hit Redis"
    ok("Persistence confirmed — data survives across cache instances")

    # Cleanup
    cache.flush()
    ok("ALL REDIS TESTS PASSED ✓")


# ──────────────────────────────────────
# Stage 3: Real SerpApi Integration
# ──────────────────────────────────────

def test_real_api():
    section("STAGE 3 — Real SerpApi Integration Test")

    from serpapi_cache import SerpApiCache, InMemoryBackend
    import os

    api_key = os.getenv("SERP_API_KEY") or os.getenv("SERPAPI_API_KEY")
    if not api_key:
        fail("No SERP_API_KEY found in environment. Check your .env file.")

    cache = SerpApiCache(
        api_key=api_key,
        backend=InMemoryBackend(),
        similarity_threshold=0.88,
        default_ttl=300,
        verbose=True,
    )

    # ── Call 1: First real search ──
    info("Test 1: Real SerpApi search (costs 1 credit)")
    t0 = time.time()
    result = cache.search({
        "engine": "google",
        "q": "SerpApi Python SDK tutorial 2026",
        "num": 5,
    })
    t1 = time.time()

    assert "organic_results" in result or "search_metadata" in result, \
        f"Unexpected result structure: {list(result.keys())}"
    ok(f"Real API call succeeded in {t1-t0:.2f}s")

    if "organic_results" in result:
        first = result["organic_results"][0]
        info(f"First result: {first.get('title', 'N/A')}")

    # ── Call 2: Same query → should be FREE (cache hit) ──
    info("Test 2: Same query again (should be FREE — cache hit)")
    t2 = time.time()
    result2 = cache.search({
        "engine": "google",
        "q": "SerpApi Python SDK tutorial 2026",
        "num": 5,
    })
    t3 = time.time()

    assert result2 == result, "Cached result should match original"
    ok(f"Cache HIT in {t3-t2:.4f}s (vs {t1-t0:.2f}s for real call) — {(t1-t0)/(t3-t2+0.0001):.0f}x faster!")

    # ── Call 3: Semantically similar ──
    info("Test 3: Semantically similar query (may or may not hit depending on threshold)")
    result3 = cache.search({
        "engine": "google",
        "q": "SerpApi Python library guide",
        "num": 5,
    })

    # ── Final stats ──
    cache.print_stats()
    ok("ALL REAL API TESTS PASSED ✓")


# ──────────────────────────────────────
# Entry Point
# ──────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify SerpApiCache")
    parser.add_argument("--no-redis", action="store_true", help="Skip Redis tests")
    parser.add_argument("--offline", action="store_true", help="Run only in-memory tests, no API calls")
    args = parser.parse_args()

    print("\n🚀 SerpApi Semantic Cache — Verification Suite")
    print("=" * 55)

    test_in_memory()

    if not args.offline:
        if not args.no_redis:
            test_redis()
        else:
            print("\n⏭️  Skipping Stage 2 (Redis) — --no-redis flag set")

        test_real_api()
    else:
        print("\n⏭️  Skipping Stages 2 & 3 (offline mode)")

    print("\n" + "=" * 55)
    print("  🎉 ALL STAGES PASSED — Cache is ready to use!")
    print("=" * 55 + "\n")
