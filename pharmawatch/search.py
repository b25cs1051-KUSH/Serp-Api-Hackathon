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

def _get_cache(verbose: bool = True) -> SerpApiCache:
    """Build a SerpApiCache instance. Redis auto-fallback is handled by the cache itself."""
    return SerpApiCache(
        api_key=os.getenv("SERP_API_KEY"),
        similarity_threshold=0.88,
        default_ttl=_PRICE_TTL,
        verbose=verbose,
    )


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
