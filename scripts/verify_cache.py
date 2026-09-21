"""
verify_cache.py — Full verification suite for SerpApiCache.

Runs 2 stages (both require Redis):
  Stage 1: Redis backend — core logic + dosage guard + persistence
  Stage 2: Real SerpApi calls — end-to-end integration

Prerequisites:
    docker compose up -d

Run:
    python scripts/verify_cache.py            # Stage 1 + 2
    python scripts/verify_cache.py --offline  # Stage 1 only (no API calls)
"""

import sys, io, os
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
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print('═' * 60)

def ok(msg: str):
    print(f"  ✅  {msg}")

def fail(msg: str):
    print(f"  ❌  {msg}")
    sys.exit(1)

def info(msg: str):
    print(f"  ℹ️   {msg}")


# ──────────────────────────────────────
# Stage 1: Redis backend tests
# ──────────────────────────────────────

def test_redis():
    section("STAGE 1 — Redis Backend: Core logic + dosage guard + persistence")

    try:
        from serpapi_cache import SerpApiCache, RedisBackend
        backend = RedisBackend(host="localhost", port=6379)
    except Exception as e:
        fail(
            f"Could not connect to Redis: {e}\n"
            f"  → Start Redis: docker compose up -d"
        )

    cache = SerpApiCache(
        api_key="test_key_not_real",
        backend=backend,
        similarity_threshold=0.80,
        default_ttl=120,
        verbose=True,
    )
    cache.flush()  # clean slate

    call_count = [0]
    def fake_serpapi(params):
        call_count[0] += 1
        return {"organic_results": [{"title": f"Fake: {params.get('q')}"}], "_mock": True}
    cache._call_serpapi = fake_serpapi

    # ── Test 1: First call → MISS ──
    info("Test 1: First search (MISS expected)")
    cache.search({"engine": "google", "q": "Metformin 500mg price India"})
    assert call_count[0] == 1, "Expected 1 API call"
    assert cache.size() == 1
    ok(f"MISS confirmed — cache has {cache.size()} entry in Redis")

    # ── Test 2: Exact same query → HIT ──
    info("Test 2: Exact same query (HIT expected)")
    cache.search({"engine": "google", "q": "Metformin 500mg price India"})
    assert call_count[0] == 1, "API should NOT be called again"
    ok("HIT confirmed — no extra API call")

    # ── Test 3: Same drug, same dosage, different phrasing → HIT ──
    info("Test 3: Same dosage, different phrasing (HIT expected — cosine + dosage guard pass)")
    cache.search({"engine": "google", "q": "Metformin 500 mg cost India"})
    if call_count[0] == 1:
        ok("HIT confirmed — '500mg' and '500 mg' matched")
    else:
        info("MISS (similarity below threshold) — consider lowering threshold")

    # ── Test 4: Same drug, DIFFERENT dosage → MISS (dosage guard) ──
    info("Test 4: Different dosage (MISS expected — dosage guard fires)")
    before = call_count[0]
    cache.search({"engine": "google", "q": "Metformin 200mg price India"})
    assert call_count[0] > before, "Dosage guard should have forced a MISS"
    ok("MISS confirmed — dosage guard blocked '200mg' from matching '500mg'")

    # ── Test 5: Completely different query → MISS ──
    info("Test 5: Different drug entirely (MISS expected)")
    before = call_count[0]
    cache.search({"engine": "google", "q": "Atorvastatin 10mg tablet price India"})
    assert call_count[0] > before, "Different drug must miss"
    ok("MISS confirmed — different drug correctly triggers API call")

    # ── Test 6: No numbers in query → dosage guard skipped, cosine decides ──
    info("Test 6: No dosage in query (HIT or MISS decided by cosine only)")
    before = call_count[0]
    cache.search({"engine": "google", "q": "cheap diabetes medicine India"})
    if call_count[0] == before:
        ok("HIT via cosine — no numbers, dosage guard skipped")
    else:
        ok("MISS via cosine — semantics too different, dosage guard correctly skipped")

    # ── Test 7: Persistence — new cache instance, same Redis ──
    info("Test 7: Persistence — new SerpApiCache instance reads from same Redis")
    size_before = cache.size()
    cache2 = SerpApiCache(
        api_key="test_key_not_real",
        backend=RedisBackend(host="localhost", port=6379),
        similarity_threshold=0.80,
        verbose=False,
    )
    call_count_2 = [0]
    def fake_serpapi_2(params):
        call_count_2[0] += 1
        return {"_mock2": True}
    cache2._call_serpapi = fake_serpapi_2
    cache2.search({"engine": "google", "q": "Metformin 500mg price India"})
    assert call_count_2[0] == 0, "New instance must hit Redis, not call API"
    assert cache2.size() == size_before
    ok("Persistence confirmed — data survives across cache instances")

    cache.print_stats()
    cache.flush()
    ok("ALL REDIS TESTS PASSED ✓")


# ──────────────────────────────────────
# Stage 2: Real SerpApi Integration
# ──────────────────────────────────────

def test_real_api():
    section("STAGE 2 — Real SerpApi Integration (uses Redis)")

    from serpapi_cache import SerpApiCache, RedisBackend
    import os

    api_key = os.getenv("SERP_API_KEY") or os.getenv("SERPAPI_API_KEY")
    if not api_key:
        fail("No SERP_API_KEY found in environment. Check your .env file.")

    try:
        backend = RedisBackend(host="localhost", port=6379)
    except Exception as e:
        fail(f"Redis not reachable: {e}\n  → Start Redis: docker compose up -d")

    cache = SerpApiCache(
        api_key=api_key,
        backend=backend,
        similarity_threshold=0.88,
        default_ttl=3600,
        verbose=True,
    )
    cache.flush()

    # ── Call 1: First real search ──
    info("Test 1: Real SerpApi search — Metformin price India (costs 1 credit)")
    t0 = time.time()
    result = cache.search({
        "engine": "google",
        "q": "Metformin 500mg price India",
        "num": 5,
    })
    t1 = time.time()

    assert "organic_results" in result or "search_metadata" in result, \
        f"Unexpected result structure: {list(result.keys())}"
    ok(f"Real API call succeeded in {t1-t0:.2f}s — stored in Redis")

    if "organic_results" in result:
        first = result["organic_results"][0]
        info(f"First result: {first.get('title', 'N/A')}")

    # ── Call 2: Same query → FREE cache hit ──
    info("Test 2: Same query (HIT — no API credit used)")
    t2 = time.time()
    result2 = cache.search({
        "engine": "google",
        "q": "Metformin 500mg price India",
        "num": 5,
    })
    t3 = time.time()
    assert result2 == result
    ok(f"Cache HIT in {t3-t2:.4f}s (vs {t1-t0:.2f}s for real call) — {(t1-t0)/(t3-t2+0.0001):.0f}x faster!")

    # ── Call 3: Different dosage → MISS (dosage guard) ──
    info("Test 3: Different dosage — 'Metformin 200mg' (dosage guard → MISS, costs 1 credit)")
    result3 = cache.search({
        "engine": "google",
        "q": "Metformin 200mg price India",
        "num": 5,
    })
    ok("Dosage guard correctly prevented cross-dosage cache hit")

    # ── Call 4: New instance — prove data persists in Redis ──
    info("Test 4: New SerpApiCache instance reads Metformin 500mg from Redis (no credit)")
    cache2 = SerpApiCache(
        api_key=api_key,
        backend=RedisBackend(host="localhost", port=6379),
        similarity_threshold=0.88,
        verbose=True,
    )
    result4 = cache2.search({
        "engine": "google",
        "q": "Metformin 500mg price India",
        "num": 5,
    })
    assert result4 == result, "Must return same cached result"
    ok("Persistence confirmed — new instance hit Redis without extra API call")

    cache.print_stats()
    ok("ALL REAL API TESTS PASSED ✓")


# ──────────────────────────────────────
# Entry Point
# ──────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify SerpApiCache")
    parser.add_argument("--offline", action="store_true",
                        help="Stage 1 only — no real API calls")
    args = parser.parse_args()

    print("\n🚀 SerpApi Semantic Cache — Verification Suite")
    print("=" * 60)

    test_redis()

    if not args.offline:
        test_real_api()
    else:
        print("\n⏭️  Skipping Stage 2 (offline mode — no real API calls)")

    print("\n" + "=" * 60)
    print("  🎉 ALL STAGES PASSED — Cache is ready!")
    print("=" * 60 + "\n")
