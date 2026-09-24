"""
search.py — SerpApi query layer for PharmaWatch.

Wraps SerpApiCache.search() with PharmaWatch-specific query patterns.
All results are raw SerpApi JSON — distiller.py cleans them.
"""

import os
from typing import Optional

from dotenv import load_dotenv

from serpapi_cache import SerpApiCache, RedisBackend

load_dotenv()

# ─────────────────────────────────────────────
# Shared cache instance (module-level singleton)
# ─────────────────────────────────────────────

_PRICE_TTL = 86_400  # 24 hours — prices cached per day
_cache_instance: Optional[SerpApiCache] = None


def _get_cache(verbose: bool = True) -> SerpApiCache:
    """Build or return singleton SerpApiCache instance. Redis auto-fallback handled internally."""
    global _cache_instance
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

def search_prices(medicine_name: str, verbose: bool = True) -> dict:
    """
    Search for prices of a medicine across Indian pharma platforms.

    Engine  : google_shopping
    Query   : "{medicine_name} tablet price India"
    TTL     : 86400 (24 hours)
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
    return cache.search(params, ttl=_PRICE_TTL)


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
    stores = res.get("product_results", {}).get("stores", [])
    if not stores:
        return None

    if target_platform:
        target_clean = target_platform.lower().replace(" ", "")
        for store in stores:
            if isinstance(store, dict) and store.get("link"):
                store_name = (store.get("name") or "").lower().replace(" ", "")
                if target_clean in store_name or store_name in target_clean:
                    return store["link"]

    if isinstance(stores[0], dict) and stores[0].get("link"):
        return stores[0]["link"]
    return None


