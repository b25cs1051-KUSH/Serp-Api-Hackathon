"""
search.py — SerpApi query layer for PharmaWatch.

Wraps SerpApiCache.search() with PharmaWatch-specific query patterns.
All results are raw SerpApi JSON — distiller.py cleans them.
"""

import os
import threading
from typing import Optional

from dotenv import load_dotenv

from serpapi_cache import SerpApiCache, RedisBackend

load_dotenv()

# ─────────────────────────────────────────────
# Shared cache instance (module-level singleton)
# ─────────────────────────────────────────────

_PRICE_TTL = 86_400  # 24 hours — prices cached per day
_cache_instance: Optional[SerpApiCache] = None
_cache_lock = threading.Lock()


def _get_cache(verbose: bool = True) -> SerpApiCache:
    """Build or return singleton SerpApiCache instance. Redis auto-fallback handled internally."""
    global _cache_instance
    with _cache_lock:  # the API's warm-up thread and the first request can arrive together
        if _cache_instance is None:
            _cache_instance = SerpApiCache(
                api_key=os.getenv("SERP_API_KEY"),
                similarity_threshold=0.88,
                default_ttl=_PRICE_TTL,
                verbose=verbose,
            )
        else:
            _cache_instance.verbose = verbose
        return _cache_instance


def warm_up(verbose: bool = True) -> float:
    """Call once at app start: connects Redis and pre-loads the embedding model. Returns ms."""
    return _get_cache(verbose=verbose).warm_up()


# ─────────────────────────────────────────────
# P2.1 — Primary price search via google_shopping
# ─────────────────────────────────────────────

def search_prices(medicine_name: str, verbose: bool = True, exact_only: bool = False) -> dict:
    """
    Search for prices of a medicine across Indian pharma platforms.

    Engine  : google_shopping
    Query   : "{medicine_name} price"
    TTL     : 86400 (24 hours)
    exact_only : cache hit only on this exact medicine name (no similarity match) —
                 used for brand names from compositions.md
    Returns : Raw SerpApi shopping JSON (pass to distiller.distill_shopping_results)
    """
    cache = _get_cache(verbose=verbose)
    params = {
        "engine": "google_shopping",
        "q": f"{medicine_name} price",
        "google_domain": "google.co.in",
        "gl": "in",
        "hl": "en",
    }
    return cache.search(params, ttl=_PRICE_TTL, exact_only=exact_only)


# ─────────────────────────────────────────────
# P2.2 — Per-platform fallback via google search
# ─────────────────────────────────────────────

_PLATFORM_DOMAINS = {
    "1mg": "1mg.com",
    "pharmeasy": "pharmeasy.in",
    "netmeds": "netmeds.com",
    "apollo": "apollopharmacy.in",
    "medplus": "medplusbazaar.com",
}


def search_platform_price(
    medicine_name: str,
    platform: str,
    verbose: bool = True,
) -> Optional[dict]:
    """
    Fallback: search a specific platform directly via google engine.

    Use when google_shopping misses a platform entirely.

    Args:
        medicine_name : e.g. "Metformin 500mg"
        platform      : key from _PLATFORM_DOMAINS, e.g. "1mg"
    Returns:
        Raw SerpApi google JSON, or None if platform key is unknown.
    """
    domain = _PLATFORM_DOMAINS.get(platform.lower())
    if not domain:
        return None

    cache = _get_cache(verbose=verbose)
    params = {
        "engine": "google",
        "q": f"{medicine_name} price site:{domain}",
        "google_domain": "google.co.in",
        "gl": "in",
        "hl": "en",
    }
    return cache.search(params, ttl=_PRICE_TTL)


# ─────────────────────────────────────────────
# P2.3 — Extract exact 'Visit Site' Merchant URL via Page Token
# ─────────────────────────────────────────────

def get_direct_merchant_link(
    page_token: str,
    target_platform: Optional[str] = None,
    verbose: bool = False,
) -> Optional[str]:
    """
    Query SerpApi google_immersive_product with page_token to extract the exact
    blue 'Visit site' merchant landing page URL for the target_platform (e.g. 1mg, Apollo Pharmacy).
    Result is cached in SerpApiCache for 24 hours.
    """
    if not page_token:
        return None

    cache = _get_cache(verbose=verbose)
    params = {
        "engine": "google_immersive_product",
        "page_token": page_token,
    }
    res = cache.search(params, ttl=_PRICE_TTL)
    return pick_store_link(res.get("product_results", {}).get("stores", []), target_platform)


def pick_store_link(stores: list, target_platform: Optional[str]) -> Optional[str]:
    """
    The store link belonging to `target_platform` (same platform detection as the distiller:
    'Apollo 247' / apollopharmacy.in → 'Apollo Pharmacy'). None if that platform isn't among the
    stores — never another pharmacy's page. Without a target, the first store with a link.
    """
    from pharmawatch.distiller import identify_platform

    with_links = [s for s in stores or [] if isinstance(s, dict) and s.get("link")]
    if not target_platform:
        return with_links[0]["link"] if with_links else None
    for store in with_links:
        if identify_platform(store.get("name") or "", store["link"]) == target_platform:
            return store["link"]
    return None


